"""Release a private project into an existing local public Git repository."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile

from common import Error, write_json
from git_branch import prepare
from nix_worker import verify
from policy import policy_at
from source import export


def public_repository(source, repository):
    source, repository = source.resolve(), repository.resolve()
    if (
        source == repository
        or repository.is_relative_to(source)
        or source.is_relative_to(repository)
    ):
        raise Error(
            "Private and public repositories must be separate directories"
        )
    git = os.environ.get("PUBLICATE_GIT")
    if not git:
        raise Error("Run the Nix-packaged publicate command")

    def invoke(*args, check=True, data=None):
        return subprocess.run(
            [
                git,
                "--no-optional-locks",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "merge.autoStash=false",
                "-C",
                str(repository),
                *args,
            ],
            check=check,
            text=True,
            input=data,
            stdout=subprocess.PIPE,
        )

    def output(*args):
        return invoke(*args).stdout.strip()

    git_directory = Path(output("rev-parse", "--absolute-git-dir"))
    private_common = subprocess.check_output(
        [
            git,
            "-C",
            str(source),
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ],
        text=True,
    ).strip()
    if (
        Path(private_common).resolve()
        == Path(
            output("rev-parse", "--path-format=absolute", "--git-common-dir")
        ).resolve()
    ):
        raise Error(
            "Private and public repositories must have independent Git history"
        )
    bare = output("rev-parse", "--is-bare-repository") == "true"
    if not bare:
        if Path(output("rev-parse", "--show-toplevel")).resolve() != repository:
            raise Error("Supply the root of the public Git checkout")
        if output("status", "--porcelain", "--untracked-files=all"):
            raise Error(
                "Public checkout must be clean; no files were discarded"
            )
    branch_ref = output("symbolic-ref", "HEAD")
    if not branch_ref.startswith("refs/heads/"):
        raise Error("Public repository must select a branch")
    return invoke, git_directory, bare, branch_ref


def release(
    source,
    repository,
    version,
    policy_path,
    run_directory=None,
    fresh=False,
    push=False,
):
    source, repository = source.resolve(), repository.resolve()
    invoke, git_directory, bare, branch_ref = public_repository(
        source, repository
    )
    policy = policy_at(policy_path)
    if policy.get("publish", {}).get("version_branches", True):
        from versions import snapshot_release

        return snapshot_release(
            source,
            repository,
            version,
            policy_path,
            policy,
            (invoke, git_directory, bare, branch_ref),
            verify,
            run_directory,
            fresh,
            push,
        )
    branch = branch_ref.removeprefix("refs/heads/")
    tag = "refs/tags/" + version if version is not None else None
    if tag:
        invoke("check-ref-format", tag)
    if push:
        invoke("remote", "get-url", "origin")
    replace_main = policy.get("publish", {}).get("replace_main", False)
    if replace_main and branch != "main":
        raise Error("publish.replace_main requires the public main branch")
    run_root = (
        run_directory
        or Path(
            os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))
        )
        / "publicate"
    ).resolve()
    if run_root.is_relative_to(source) or run_root.is_relative_to(repository):
        raise Error("Keep release run directories outside both repositories")
    run_root.mkdir(parents=True, exist_ok=True)
    operation = "release" if tag else "sync"
    run = Path(tempfile.mkdtemp(prefix=operation + "-", dir=run_root))
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
        git_directory,
        branch,
        record,
        policy,
        policy_path,
        update_branch=False,
        replace_history=replace_main,
    )
    existing = None
    if tag:
        existing = invoke("rev-parse", "--verify", "--quiet", tag, check=False)
        if existing.returncode not in (0, 1):
            existing.check_returncode()
        if (
            existing.returncode == 0
            and existing.stdout.strip() != snapshot["commit"]
        ):
            raise Error(
                f"Release version already exists: {version}; choose a new version"
            )
    if bare:
        invoke(
            "update-ref",
            branch_ref,
            snapshot["commit"],
            snapshot["previous"] or "0" * len(snapshot["commit"]),
        )
    elif replace_main:
        current = invoke(
            "rev-parse", "--verify", "--quiet", branch_ref, check=False
        )
        if current.returncode not in (0, 1):
            current.check_returncode()
        if (current.stdout.strip() or None) != snapshot["previous"]:
            raise Error("Public branch changed during verification")
        if invoke("symbolic-ref", "HEAD").stdout.strip() != branch_ref:
            raise Error("Public checkout switched branches during verification")
        if invoke(
            "status", "--porcelain", "--untracked-files=all", "--ignored"
        ).stdout.strip():
            raise Error(
                "Replacement requires a clean public checkout, including ignored files"
            )
        invoke("reset", "--hard", snapshot["commit"])
    else:
        invoke(
            "merge", "--ff-only", "--no-overwrite-ignore", snapshot["commit"]
        )
    if existing and existing.returncode == 1:
        invoke(
            "update-ref", tag, snapshot["commit"], "0" * len(snapshot["commit"])
        )
    result = {
        "status": "prepared",
        "repository": str(repository),
        "branch": branch,
        "version": version,
        "commit": snapshot["commit"],
        "runDirectory": str(run),
        "source": str(candidate),
        "verification": str(record),
        "replaceMain": replace_main,
    }
    write_json(run / (operation + ".json"), result)
    if push:
        refs = [("+" if replace_main else "") + branch_ref + ":" + branch_ref]
        if tag:
            refs.append(tag + ":" + tag)
        invoke(
            "push",
            "--atomic",
            "--no-force",
            "--no-mirror",
            "--no-follow-tags",
            "--signed=false",
            "origin",
            *refs,
        )
        result["status"] = "published"
        write_json(run / (operation + ".json"), result)
    return result


def sync(
    source,
    repository,
    policy_path,
    run_directory=None,
    fresh=False,
    push=False,
    version=None,
):
    return release(
        source, repository, version, policy_path, run_directory, fresh, push
    )
