"""Maintain a bare comparison and publication cache for a configured Git URL."""

import os
from pathlib import Path
import subprocess

from common import Error, digest
from versions import SEMVER, version_state


def repository_for(source, publication):
    url = publication.get("repository")
    if url is None:
        raise Error("Supply a public repository or set publish.repository")
    git = os.environ.get("PUBLICATE_GIT")
    if not git:
        raise Error("Run the Nix-packaged publicate command")
    base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    repository = (
        base / "publicate" / "remotes" / digest(url.encode())
    ).resolve()
    if repository.is_relative_to(source):
        raise Error("Keep the publication cache outside the private project")
    if not repository.exists():
        repository.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [git, "init", "--bare", "--quiet", str(repository)], check=True
        )
        subprocess.run(
            [git, "-C", str(repository), "remote", "add", "origin", url],
            check=True,
        )

    def invoke(*args, check=True):
        return subprocess.run(
            [
                git,
                "-c",
                "core.hooksPath=/dev/null",
                "-C",
                str(repository),
                *args,
            ],
            check=check,
            text=True,
            stdout=subprocess.PIPE,
        )

    if invoke("rev-parse", "--is-bare-repository").stdout.strip() != "true":
        raise Error("Publication cache must be a bare Git repository")
    if invoke("remote", "get-url", "origin").stdout.strip() != url:
        raise Error("Publication cache has a different origin")
    with version_state(repository):
        invoke(
            "remote",
            "set-url",
            "--push",
            "origin",
            publication.get("push_url", url),
        )
        invoke(
            "fetch",
            "--prune",
            "--tags",
            "origin",
            "+refs/heads/*:refs/remotes/origin/*",
        )
        tip = invoke(
            "rev-parse",
            "--verify",
            "--quiet",
            "refs/remotes/origin/main",
            check=False,
        )
        if tip.returncode == 0:
            invoke("update-ref", "refs/heads/main", tip.stdout.strip())
        elif tip.returncode == 1:
            invoke("update-ref", "-d", "refs/heads/main")
        else:
            tip.check_returncode()
        if publication.get("version_branches", True):
            remote_versions = {}
            for line in invoke(
                "for-each-ref",
                "--format=%(refname)\t%(objectname)",
                "refs/remotes/origin",
            ).stdout.splitlines():
                ref, oid = line.split("\t")
                name = ref.removeprefix("refs/remotes/origin/")
                if SEMVER.fullmatch(name):
                    remote_versions[name] = oid
            for name, oid in remote_versions.items():
                invoke("update-ref", "refs/heads/" + name, oid)
            for name in invoke(
                "for-each-ref",
                "--format=%(refname:strip=2)",
                "refs/heads",
            ).stdout.splitlines():
                if SEMVER.fullmatch(name) and name not in remote_versions:
                    invoke("update-ref", "-d", "refs/heads/" + name)
        invoke("symbolic-ref", "HEAD", "refs/heads/main")
    return repository
