"""Shared path constraints, hashing and subprocess execution."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess

VERSION = Path(__file__).with_name("VERSION").read_text().strip()
BLACKOUT = {
    ".git",
    ".agents",
    "AGENTS.md",
    "SKILL.md",
    "__pycache__",
    ".publicate",
    "publicate.toml",
    "publish.sh",
    "review.sh",
    "publicate",
    "tickets",
}


class Error(Exception):
    pass


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def git_environment(git, source):
    env = dict(os.environ)
    if "GIT_SSH_COMMAND" in env:
        return env
    command = subprocess.run(
        [git, "-C", str(source), "config", "--get", "core.sshCommand"],
        text=True,
        stdout=subprocess.PIPE,
        env=env,
    )
    if command.returncode == 0:
        env["GIT_SSH_COMMAND"] = command.stdout.rstrip("\n")
    elif command.returncode != 1:
        command.check_returncode()
    return env


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def safe_path(value):
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or path == PurePosixPath(".")
    ):
        raise Error(f"Expected a relative path within the project: {value}")
    return path


def blocked(value, policy_path, *, public_agents=False):
    if (
        value == "AGENTS.md"
        and public_agents
        and policy_path.name != "AGENTS.md"
    ):
        return False
    return bool(
        set(PurePosixPath(value).parts) & (BLACKOUT | {policy_path.name})
    )
