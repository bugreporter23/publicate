"""Inspect candidate paths, pinned inputs and declared text rules."""

import json
import re
from urllib.parse import parse_qsl, urlsplit

from common import Error, blocked, safe_path
from prose import prose_findings

PROFILES = {
    "public-v1": {
        "home-path": r"/(?:(?:home|Users)/[A-Za-z0-9_.-]+|root)(?:/[A-Za-z0-9_.-]|\b)",
        "conversation": r"(?i)\b(?:as\s+(?:requested|discussed)|the\s+user\s+(?:said|asked|wanted)|our\s+conversation|per\s+your\s+request)\b",
        "emotional-opening": r"(?im)^[ \t]*(?:[#/*;]+[ \t]*)?(?:ugh|wtf|sorry|fuck)\b",
    },
}


def text_rules(style):
    profile = style.get("profile")
    if profile is not None and profile not in PROFILES:
        raise Error(f"Unknown style profile: {profile}")
    rules = list(PROFILES.get(profile, {}).items())
    rules.extend(
        (f"forbid-{index + 1}", pattern)
        for index, pattern in enumerate(style.get("forbid", []))
    )
    compiled = []
    for name, pattern in rules:
        try:
            compiled.append((name, re.compile(pattern)))
        except re.error:
            raise Error(f"Invalid text rule: {name}") from None
    return compiled


def validate_style(style):
    if not isinstance(style, dict) or set(style) - {
        "profile",
        "forbid",
        "prose",
    }:
        raise Error("style supports profile, forbid and prose")
    if not isinstance(style.get("prose", False), bool):
        raise Error("style.prose must be a boolean")
    if not isinstance(style.get("forbid", []), list) or any(
        not isinstance(pattern, str) for pattern in style.get("forbid", [])
    ):
        raise Error("style.forbid must contain regex strings")
    text_rules(style)


def style_findings(text, path, style):
    findings = [
        (text.count("\n", 0, match.start()) + 1, name)
        for name, pattern in text_rules(style)
        for match in pattern.finditer(text)
    ]
    if style.get("prose", False) and path.suffix.lower() in {
        ".md",
        ".markdown",
    }:
        findings.extend(prose_findings(text))
    return sorted(set(findings))


def style_check(root, policy):
    style = dict(policy.get("style", {}), prose=False)
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            findings = style_findings(text, path, style)
            if findings:
                line, name = findings[0]
                raise Error(
                    f"Source rule {name} failed: {path.relative_to(root)}:{line}"
                )


def lock_check(root):
    lock = json.loads((root / "flake.lock").read_text())
    for name, node in lock["nodes"].items():
        for info in (node.get("locked", {}), node.get("original", {})):
            kind = info.get("type")
            if kind == "indirect":
                raise Error(
                    f"Input {name} needs a public pin, not a registry lookup"
                )
            if kind == "path":
                path = info.get("path", "")
                safe_path(path)
                if (
                    not (root / path).resolve().is_relative_to(root)
                    or not (root / path).exists()
                ):
                    raise Error(
                        f"Input {name} needs an included source or public release"
                    )
            url = info.get("url", "")
            if url:
                try:
                    parsed = urlsplit(url)
                    query = parse_qsl(
                        parsed.query,
                        keep_blank_values=True,
                        strict_parsing=True,
                    )
                    allowed = {
                        "rev",
                        "ref",
                        "dir",
                        "narHash",
                        "shallow",
                        "submodules",
                        "lfs",
                        "allRefs",
                        "lastModified",
                        "revCount",
                    }
                    if (
                        parsed.scheme not in {"https", "git+https"}
                        or not parsed.hostname
                    ):
                        raise ValueError()
                    if (
                        parsed.username is not None
                        or parsed.fragment
                        or any(c.isspace() for c in url)
                    ):
                        raise ValueError()
                    if len(query) != len(dict(query)) or any(
                        key not in allowed for key, _ in query
                    ):
                        raise ValueError()
                except ValueError:
                    raise Error(
                        f"Input {name} needs an anonymous HTTPS URL with supported flake parameters"
                    ) from None


def check_candidate(candidate, policy, policy_path):
    if not candidate.is_dir():
        raise Error("Candidate directory does not exist")
    public_agents = (
        "AGENTS.md" in policy.get("export", {}).get("files", {}).values()
    )
    for path in candidate.rglob("*"):
        name = path.relative_to(candidate).as_posix()
        if (
            name == "AGENTS.md"
            and public_agents
            and (path.is_symlink() or not path.is_file())
        ):
            raise Error("Public agent guidance must be a regular file")
        if blocked(name, policy_path, public_agents=public_agents):
            raise Error("Candidate still contains mandatory blackout paths")
        if path.is_symlink():
            try:
                if path.readlink().is_absolute() or not path.resolve(
                    strict=True
                ).is_relative_to(candidate):
                    raise Error(
                        f"Candidate symlink escapes the public view: {path.relative_to(candidate)}"
                    )
            except (OSError, RuntimeError):
                raise Error(
                    f"Candidate symlink requires missing material: {path.relative_to(candidate)}"
                ) from None
    lock_check(candidate)
    style_check(candidate, policy)
    if policy.get("patches", {}).get("series"):
        from patch_check import require_clean_patches

        require_clean_patches(
            candidate,
            policy,
            policy_path,
            {
                path.relative_to(candidate).as_posix(): path
                for path in candidate.rglob("*")
                if path.is_file()
            },
        )
