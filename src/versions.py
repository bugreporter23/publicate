"""Publish and retire independently rooted SemVer snapshots."""

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from common import Error, write_json
from git_branch import prepare
from policy import policy_at
from source import export


NUMBER = r"(?:0|[1-9][0-9]*)"
IDENTIFIER = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
SEMVER = re.compile(
    rf"v({NUMBER})\.({NUMBER})\.({NUMBER})"
    rf"(?:-({IDENTIFIER}(?:\.{IDENTIFIER})*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
)


def version_key(version):
    match = SEMVER.fullmatch(version) if isinstance(version, str) else None
    if not match:
        raise Error("Choose a SemVer branch such as v1.2.3")
    major, minor, patch, pre, _ = match.groups()
    identifiers = tuple(
        (0, int(part)) if part.isdigit() else (1, part)
        for part in (pre.split(".") if pre else [])
    )
    return (int(major), int(minor), int(patch), pre is None, identifiers)


def branch_versions(refs):
    return {
        ref.removeprefix("refs/heads/"): oid
        for ref, oid in refs.items()
        if ref.startswith("refs/heads/")
        and SEMVER.fullmatch(ref.removeprefix("refs/heads/"))
    }


def local_refs(invoke):
    return dict(
        line.split("\t")
        for line in invoke(
            "for-each-ref",
            "--format=%(refname)\t%(objectname)",
            "refs/heads",
            "refs/tags",
        ).stdout.splitlines()
    )


def remote_refs(invoke):
    return {
        ref: oid
        for oid, ref in (
            line.split("\t")
            for line in invoke(
                "ls-remote", "--heads", "--tags", "origin"
            ).stdout.splitlines()
        )
    }


def require_main(invoke, bare, branch_ref):
    if branch_ref != "refs/heads/main":
        raise Error("Version snapshots require the public main branch")
    direct_ref(invoke, branch_ref)
    if (
        len(invoke("worktree", "list", "--porcelain").stdout.split("worktree "))
        > 2
    ):
        raise Error(
            "Version operations require a public repository without linked worktrees"
        )
    if (
        not bare
        and invoke(
            "status", "--porcelain", "--untracked-files=all", "--ignored"
        ).stdout.strip()
    ):
        raise Error(
            "Version operations require a clean checkout, including ignored files"
        )


def direct_ref(invoke, ref):
    result = invoke("symbolic-ref", "--quiet", ref, check=False)
    if result.returncode == 0:
        raise Error("Version operations require direct references")
    if result.returncode != 1:
        result.check_returncode()


def independent_snapshot(invoke, oid):
    parents = invoke("rev-list", "--parents", "-n", "1", oid).stdout.split()
    metadata = invoke(
        "show", "-s", "--format=%an <%ae>%n%cn <%ce>%n%at %ct%n%B", oid
    ).stdout.strip()
    return len(parents) == 1 and metadata == (
        "user.name <user.email>\nuser.name <user.email>\n0 0\npublicate"
    )


@contextmanager
def version_state(directory):
    with (directory / "publicate-versions.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = directory / "publicate-versions.json"
        state = (
            json.loads(path.read_text()) if path.exists() else {"versions": {}}
        )
        yield state, path


def save_state(path, state):
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, prefix=".publicate-versions-", delete=False
    ) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(state, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink()
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def update_refs(invoke, changes, old_refs, oid_length, *, verify=()):
    zero = "0" * oid_length
    lines = ["start"]
    for ref in verify:
        lines.append(f"verify {ref} {old_refs.get(ref, zero)}")
    for ref, new in changes.items():
        old = old_refs.get(ref, zero)
        lines.append(
            f"update {ref} {new} {old}" if new else f"delete {ref} {old}"
        )
    lines.extend(["prepare", "commit"])
    invoke("update-ref", "--stdin", data="\n".join(lines) + "\n")


def push_refs(invoke, changes, baseline):
    leases = [
        "--force-with-lease=" + ref + ":" + baseline.get(ref, "")
        for ref in changes
    ]
    invoke(
        "push",
        "--atomic",
        "--no-mirror",
        "--no-follow-tags",
        "--signed=false",
        *leases,
        "origin",
        *(f"{oid or ''}:{ref}" for ref, oid in changes.items()),
    )


def snapshot_release(
    source,
    repository,
    version,
    policy_path,
    policy,
    public,
    verify,
    run_directory=None,
    fresh=False,
    push=False,
    *,
    bump_patch=False,
    bump_minor=False,
):
    version_key(version)
    if bump_minor:
        major, minor, _, _, _ = SEMVER.fullmatch(version).groups()
        version = f"v{major}.{int(minor) + 1}.0"
    invoke, directory, bare, branch_ref = public
    require_main(invoke, bare, branch_ref)
    with version_state(directory) as (state, state_path):
        refs = local_refs(invoke)
        baseline = remote_refs(invoke) if push else {}
        ref = "refs/heads/" + version
        if not bump_patch and (
            "refs/tags/" + version in refs or "refs/tags/" + version in baseline
        ):
            raise Error(
                "Version name already exists as a tag; choose a new version"
            )
        reserved = state["versions"].get(version)
        if not bump_patch and reserved and reserved.get("retired"):
            raise Error("Release version was retired; choose a new version")
        run_root = (
            run_directory
            or Path(
                os.environ.get(
                    "XDG_STATE_HOME", str(Path.home() / ".local/state")
                )
            )
            / "publicate"
        ).resolve()
        if run_root.is_relative_to(source) or run_root.is_relative_to(
            repository
        ):
            raise Error(
                "Keep release run directories outside both repositories"
            )
        run_root.mkdir(parents=True, exist_ok=True)
        run = Path(tempfile.mkdtemp(prefix="release-", dir=run_root))
        candidate, record = run / "source", run / "verification.json"
        print(f"Exporting to {candidate}", file=sys.stderr)
        export(source, candidate, policy, policy_path)
        print("Verifying exported build", file=sys.stderr)
        evidence = verify(candidate, policy, fresh, policy_path)
        write_json(record, evidence)
        if evidence["status"] != "passed":
            raise Error(f"Verification failed; inspect {record}")
        snapshot = prepare(
            candidate,
            directory,
            version,
            record,
            policy,
            policy_path,
            update_branch=False,
            replace_history=True,
        )
        commit = snapshot["commit"]
        if bump_patch:
            while True:
                ref = "refs/heads/" + version
                reserved = state["versions"].get(version)
                identities = [
                    refs.get(ref),
                    baseline.get(ref),
                    reserved.get("commit") if reserved else None,
                ]
                conflict = (
                    "refs/tags/" + version in refs
                    or "refs/tags/" + version in baseline
                    or bool(reserved and reserved.get("retired"))
                    or any(oid and oid != commit for oid in identities)
                )
                if not conflict:
                    break
                major, minor, patch, _, _ = SEMVER.fullmatch(version).groups()
                version = f"v{major}.{minor}.{int(patch) + 1}"
        identities = [
            refs.get(ref),
            baseline.get(ref),
            reserved.get("commit") if reserved else None,
        ]
        if any(oid and oid != commit for oid in identities):
            raise Error(
                f"Release version already exists: {version}; choose a new version"
            )
        require_main(invoke, bare, branch_ref)
        if invoke("symbolic-ref", "HEAD").stdout.strip() != branch_ref:
            raise Error("Public checkout switched branches during verification")
        changes = {ref: commit, branch_ref: commit}
        state["versions"][version] = {"commit": commit, "retired": False}
        state["current"] = version
        save_state(state_path, state)
        update_refs(invoke, changes, refs, len(commit))
        if not bare:
            invoke("reset", "--hard", commit)
        result = {
            "status": "prepared",
            "repository": str(repository),
            "branch": version,
            "version": version,
            "commit": commit,
            "runDirectory": str(run),
            "source": str(candidate),
            "verification": str(record),
            "versionBranches": True,
        }
        write_json(run / "release.json", result)
        if push:
            push_refs(invoke, changes, baseline)
            result["status"] = "published"
            write_json(run / "release.json", result)
        return result


def prune(
    source,
    repository,
    policy_path,
    *,
    versions=(),
    keep=None,
    keep_patches=None,
    apply=False,
    push=False,
):
    from release import public_repository

    if (
        not policy_at(policy_path)
        .get("publish", {})
        .get("version_branches", True)
    ):
        raise Error("Pruning requires publish.version_branches")
    invoke, directory, bare, branch_ref = public_repository(source, repository)
    require_main(invoke, bare, branch_ref)
    if sum((bool(versions), keep is not None, keep_patches is not None)) != 1:
        raise Error("Choose versions to prune, --keep N or --keep-patches N")
    if keep is not None and (type(keep) is not int or keep < 1):
        raise Error("--keep must retain at least one version")
    if keep_patches is not None and (
        type(keep_patches) is not int or keep_patches < 1
    ):
        raise Error("--keep-patches must retain at least one version per line")
    for version in versions:
        version_key(version)
    with version_state(directory) as (state, state_path):
        refs = local_refs(invoke)
        baseline = remote_refs(invoke) if push else {}
        available = branch_versions(refs)
        remote_versions = branch_versions(baseline)
        for version, oid in remote_versions.items():
            if version in available and available[version] != oid:
                raise Error(f"Local and remote versions differ: {version}")
            available[version] = oid
        current = state.get("current")
        main = refs.get(branch_ref)
        if push and baseline.get(branch_ref) != main:
            raise Error("Local and remote main differ; refresh before pruning")
        if available.get(current) != main:
            aliases = [v for v, oid in available.items() if oid == main]
            current = (
                max(aliases, key=lambda v: (version_key(v), v))
                if aliases
                else None
            )
        if current is None:
            raise Error("Publish a SemVer snapshot on main before pruning")
        if keep_patches is not None:
            groups = {}
            for version in available:
                groups.setdefault(version_key(version)[:2], []).append(version)
            retained = {current}
            for members in groups.values():
                newest = sorted(
                    (v for v in members if v != current),
                    key=lambda v: (version_key(v), v),
                    reverse=True,
                )
                count = keep_patches - (current in members)
                retained.update(newest[:count])
            selected = set(available) - retained
        elif keep is not None:
            newest = sorted(
                (v for v in available if v != current),
                key=lambda v: (version_key(v), v),
                reverse=True,
            )
            selected = set(available) - {current, *newest[: keep - 1]}
        else:
            selected = set(versions)
            if selected - available.keys():
                raise Error("Requested version branch does not exist")
        if current in selected:
            raise Error("Cannot prune the version selected by main")
        retired_tags = set()
        for version in selected:
            oid = available[version]
            tag = "refs/tags/" + version
            if tag in refs:
                direct_ref(invoke, tag)
                target = invoke(
                    "rev-parse", "--verify", tag + "^{commit}"
                ).stdout.strip()
                if target != oid:
                    raise Error(
                        "Version tag points to different content; cannot retire it"
                    )
                retired_tags.add(tag)
            if tag in baseline:
                if baseline.get(tag + "^{}", baseline[tag]) != oid:
                    raise Error(
                        "Remote version tag points to different content; cannot retire it"
                    )
                retired_tags.add(tag)
            if "refs/heads/" + version in refs:
                direct_ref(invoke, "refs/heads/" + version)
            if not independent_snapshot(invoke, oid):
                raise Error(
                    f"Version is not an independent snapshot: {version}"
                )
        ordered = sorted(selected, key=lambda v: (version_key(v), v))
        result = {
            "status": "planned",
            "repository": str(repository),
            "pruned": ordered,
            "current": current,
            "retiredTags": sorted(
                ref.removeprefix("refs/tags/") for ref in retired_tags
            ),
            "retained": sorted(
                set(available) - selected, key=lambda v: (version_key(v), v)
            ),
        }
        if not (apply or push) or not selected:
            return result
        for version in selected:
            state["versions"][version] = {
                "commit": available[version],
                "retired": True,
            }
        save_state(state_path, state)
        changes = {"refs/heads/" + v: None for v in ordered}
        changes.update({ref: None for ref in retired_tags})
        if push:
            remote_changes = {
                ref: oid for ref, oid in changes.items() if ref in baseline
            }
            push_refs(invoke, {**remote_changes, branch_ref: main}, baseline)
        local = {ref: None for ref in changes if ref in refs}
        if local:
            update_refs(invoke, local, refs, len(main), verify=[branch_ref])
        result["status"] = "published" if push else "pruned"
        return result
