"""Prepare an exact verified snapshot on a local public branch."""

import json
import os
from pathlib import Path
import subprocess
import tempfile

from common import Error, canonical, digest
from checks import check_candidate
from source import tree_digest


def prepare(
    candidate,
    repository,
    branch,
    record,
    policy,
    policy_path,
    *,
    update_branch=True,
    replace_history=False,
):
    git = os.environ.get("PUBLICATE_GIT")
    if not git:
        raise Error("Run the Nix-packaged publicate command")
    check_candidate(candidate, policy, policy_path)
    evidence = json.loads(record.read_text())
    expected = evidence.get("sourceDigest")
    if (
        evidence.get("status") != "passed"
        or (
            evidence.get("buildVerification") == "skipped"
            and policy.get("build", {}).get("verify", True)
        )
        or expected != tree_digest(candidate)
        or evidence.get("policyDigest") != digest(canonical(policy))
    ):
        raise Error(
            "Preparation requires a passed verification record for this tree and policy"
        )
    with tempfile.TemporaryDirectory(prefix="publicate-git-") as directory:
        scratch = Path(directory)
        (scratch / "home").mkdir()
        env = {
            "PATH": str(Path(git).parent),
            "HOME": str(scratch / "home"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_INDEX_FILE": str(scratch / "index"),
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_AUTHOR_NAME": "user.name",
            "GIT_AUTHOR_EMAIL": "user.email",
            "GIT_COMMITTER_NAME": "user.name",
            "GIT_COMMITTER_EMAIL": "user.email",
            "GIT_AUTHOR_DATE": "@0 +0000",
            "GIT_COMMITTER_DATE": "@0 +0000",
            "LANG": "C.UTF-8",
        }

        def invoke(*args, data=None, check=True):
            return subprocess.run(
                [
                    git,
                    "-c",
                    "core.hooksPath=/dev/null",
                    "-c",
                    "commit.gpgSign=false",
                    "-c",
                    "i18n.commitEncoding=UTF-8",
                    "--git-dir=" + str(repository),
                    *args,
                ],
                env=env,
                input=data,
                stdout=subprocess.PIPE,
                check=check,
            )

        def output(*args):
            return invoke(*args).stdout.decode().strip()

        if (
            output("rev-parse", "--is-bare-repository") != "true"
            and update_branch
        ):
            raise Error(
                "Preparation requires a dedicated bare public repository"
            )
        ref = "refs/heads/" + branch
        invoke("check-ref-format", ref)
        symbolic = invoke("symbolic-ref", "--quiet", ref, check=False)
        if symbolic.returncode == 0:
            raise Error("Public branch must be a direct reference")
        if symbolic.returncode != 1:
            symbolic.check_returncode()
        previous = invoke("rev-parse", "--verify", "--quiet", ref, check=False)
        if previous.returncode not in (0, 1):
            previous.check_returncode()
        parent = (
            previous.stdout.decode().strip()
            if previous.returncode == 0
            else None
        )
        if parent and output("cat-file", "-t", parent) != "commit":
            raise Error("Public branch must point to a commit")
        tree = snapshot_tree(candidate, scratch, invoke, expected)
        if (
            parent
            and not replace_history
            and output("rev-parse", parent + "^{tree}") == tree
        ):
            if output("rev-parse", ref) != parent:
                raise Error("Public branch changed during preparation")
            return {
                "status": "unchanged",
                "branch": branch,
                "commit": parent,
                "tree": tree,
                "previous": parent,
            }
        args = ["commit-tree", tree, "-m", "publicate"]
        if parent and not replace_history:
            args.extend(["-p", parent])
        commit = output(*args)
        if update_branch:
            invoke("update-ref", ref, commit, parent or "0" * len(commit))
        return {
            "status": "unchanged" if commit == parent else "prepared",
            "branch": branch,
            "commit": commit,
            "tree": tree,
            "parent": None if replace_history else parent,
            "previous": parent,
        }


def snapshot_tree(candidate, scratch, invoke, expected):
    invoke("read-tree", "--empty")
    index = bytearray()
    entries = []
    blobs = []
    for path in sorted(candidate.rglob("*")):
        name = path.relative_to(candidate).as_posix()
        if path.is_symlink():
            link = os.readlink(path)
            data, mode = os.fsencode(link), "120000"
            entries.append([name, "symlink", link])
        elif path.is_file():
            data = path.read_bytes()
            executable = bool(path.stat().st_mode & 0o111)
            mode = "100755" if executable else "100644"
            entries.append(
                [name, "executable" if executable else "file", digest(data)]
            )
        elif path.is_dir():
            if not any(path.iterdir()):
                raise Error(f"Git cannot preserve an empty directory: {name}")
            entries.append([name, "directory"])
            continue
        else:
            raise Error(f"Unsupported snapshot entry: {name}")
        frozen = scratch / ("blob-" + str(len(blobs)))
        frozen.write_bytes(data)
        blobs.append((name, mode, frozen))
    if (
        digest(canonical(entries)) != expected
        or tree_digest(candidate) != expected
    ):
        raise Error("Candidate changed during Git snapshot preparation")
    for name, mode, frozen in blobs:
        oid = invoke(
            "hash-object",
            "-w",
            "--no-filters",
            "--stdin",
            data=frozen.read_bytes(),
        ).stdout.strip()
        index.extend(
            mode.encode() + b" " + oid + b"\t" + os.fsencode(name) + b"\0"
        )
    invoke("update-index", "-z", "--index-info", data=bytes(index))
    return invoke("write-tree").stdout.decode().strip()
