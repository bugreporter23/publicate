"""Compare a selected export with the public branch without changing either repo."""

import os
from pathlib import Path
import subprocess
import tempfile

from checks import check_candidate
from git_branch import snapshot_tree
from policy import policy_at
from release import public_repository
from source import export


def diff(source, repository, policy_path):
    source, repository = source.resolve(), repository.resolve()
    public, _, _, branch_ref = public_repository(source, repository)
    policy = policy_at(policy_path)
    previous = public(
        "rev-parse", "--verify", "--quiet", branch_ref, check=False
    )
    if previous.returncode not in (0, 1):
        previous.check_returncode()
    parent = previous.stdout.strip() if previous.returncode == 0 else None
    objects = public(
        "rev-parse", "--path-format=absolute", "--git-path", "objects"
    ).stdout.strip()
    object_format = public("rev-parse", "--show-object-format").stdout.strip()
    git = os.environ["PUBLICATE_GIT"]
    with tempfile.TemporaryDirectory(prefix="publicate-diff-") as directory:
        scratch = Path(directory)
        candidate = scratch / "source"
        exported = export(source, candidate, policy, policy_path)
        check_candidate(candidate, policy, policy_path)
        (scratch / "home").mkdir()
        env = {
            "PATH": str(Path(git).parent),
            "HOME": str(scratch / "home"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_INDEX_FILE": str(scratch / "index"),
            "LANG": "C.UTF-8",
        }
        subprocess.run(
            [
                git,
                "init",
                "--bare",
                "--quiet",
                "--object-format=" + object_format,
                str(scratch / "git"),
            ],
            env=env,
            check=True,
        )
        env["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = objects

        def invoke(*args, data=None, check=True):
            return subprocess.run(
                [
                    git,
                    "-c",
                    "core.hooksPath=/dev/null",
                    "--git-dir=" + str(scratch / "git"),
                    *args,
                ],
                env=env,
                input=data,
                stdout=subprocess.PIPE,
                check=check,
            )

        invoke("read-tree", "--empty")
        baseline = parent or invoke("write-tree").stdout.decode().strip()
        tree = snapshot_tree(
            candidate, scratch, invoke, exported["sourceDigest"]
        )
        options = [
            "diff-tree",
            "--no-commit-id",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            "-r",
            baseline,
            tree,
        ]
        names = invoke(*options, "--name-status", "-z").stdout.split(b"\0")
        changes = [
            {"status": names[i].decode(), "path": os.fsdecode(names[i + 1])}
            for i in range(0, len(names) - 1, 2)
        ]
        patch = invoke(*options, "--patch", "--binary").stdout.decode(
            "utf-8", errors="replace"
        )
    return {
        "branch": branch_ref.removeprefix("refs/heads/"),
        "baseCommit": parent,
        "sourceDigest": exported["sourceDigest"],
        "tree": tree,
        "changes": changes,
        "patch": patch,
        "buildVerification": "not checked",
        "patchChecks": exported["patchChecks"],
        "patchesUnchecked": exported["patchesUnchecked"],
    }
