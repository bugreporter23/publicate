"""Load declared export, build and text policies."""

import fnmatch
import json
import re
import tomllib
from pathlib import Path

from common import Error
from checks import validate_style


def matches(path, patterns):
    return any(
        path == p
        or path.startswith(p.rstrip("/") + "/")
        or fnmatch.fnmatchcase(path, p)
        for p in patterns
    )


def policy_at(path):
    with path.open("rb") as stream:
        policy = (
            json.load(stream)
            if path.suffix == ".json"
            else tomllib.load(stream)
        )
    if policy.get("version") != 1:
        raise Error("Policy must specify version = 1")
    if not policy.get("export", {}).get("include"):
        raise Error("Declare export.include explicitly")
    outputs = policy.get("build", {}).get("outputs", [])
    if not outputs or any(
        not re.fullmatch(r"[A-Za-z0-9_.+-]+", p) for p in outputs
    ):
        raise Error("Declare build.outputs as flake output attributes")
    validate_style(policy.get("style", {}))
    publication = policy.get("publish", {})
    if not isinstance(publication, dict) or set(publication) - {
        "repository",
        "push_url",
        "replace_main",
        "version_branches",
    }:
        raise Error(
            "publish supports repository, push_url, replace_main and version_branches"
        )
    for key in ("repository", "push_url"):
        if key in publication and (
            not isinstance(publication[key], str)
            or not re.match(
                r"^(?:https://|ssh://|file://|[^/\s]+@[^/\s:]+:).+",
                publication[key],
            )
        ):
            raise Error(f"publish.{key} must be a Git URL")
    if not isinstance(publication.get("replace_main", False), bool):
        raise Error("publish.replace_main must be a boolean")
    if not isinstance(publication.get("version_branches", True), bool):
        raise Error("publish.version_branches must be a boolean")
    comments = policy.get("comments")
    patches = policy.get("patches", {})
    if not isinstance(patches, dict) or set(patches) - {"series"}:
        raise Error("patches supports series")
    series = patches.get("series", [])
    if not isinstance(series, list):
        raise Error("patches.series must be an array")
    for group in series:
        if not isinstance(group, dict) or set(group) != {
            "source",
            "source_digest",
            "patches",
        }:
            raise Error(
                "Each patch series requires source, source_digest and patches"
            )
        if not isinstance(group["source"], str) or not group["source"]:
            raise Error("Patch source must name a directory")
        if not Path(group["source"]).is_absolute():
            raise Error("Patch source must be an absolute runtime directory")
        if not isinstance(group["source_digest"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", group["source_digest"]
        ):
            raise Error("Patch source_digest must be a SHA-256 tree digest")
        if (
            not isinstance(group["patches"], list)
            or not group["patches"]
            or any(
                not isinstance(name, str) or not name
                for name in group["patches"]
            )
        ):
            raise Error("Declare an ordered nonempty patch list")
    if "comments" in policy:
        if not isinstance(comments, dict) or set(comments) - {
            "include",
            "preserve",
            "enabled",
        }:
            raise Error("comments supports enabled, include and preserve")
        if not isinstance(comments.get("enabled", True), bool):
            raise Error("comments.enabled must be a boolean")
        if "include" in comments and (
            not isinstance(comments["include"], list) or not comments["include"]
        ):
            raise Error("Declare comments.include as nonempty path patterns")
        for key in ("include", "preserve"):
            if not isinstance(comments.get(key, []), list) or any(
                not isinstance(value, str) or not value
                for value in comments.get(key, [])
            ):
                raise Error(f"comments.{key} must contain nonempty strings")
    return policy
