"""Shared path constraints, hashing and subprocess execution."""

import hashlib
import json
from pathlib import PurePosixPath
import subprocess

VERSION = "0.1.0"
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
