"""Check ordered patches against digest-pinned source without building it."""

from bisect import bisect_right
from difflib import SequenceMatcher
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from common import Error, safe_path
from comments import strip_comments


def copy_source(source, destination):
    source = source.resolve()
    if not source.is_dir():
        raise Error("Patch source must be a directory")
    for directory, directories, files in os.walk(source, followlinks=False):
        directories[:] = [name for name in directories if name != ".git"]
        for name in files:
            path = Path(directory) / name
            if name != ".git" and not path.is_symlink() and not path.is_file():
                raise Error("Patch source contains an unsupported file type")
    shutil.copytree(
        source,
        destination,
        symlinks=True,
        ignore=lambda directory, names: [".git"] if ".git" in names else [],
    )
    for path in destination.rglob("*"):
        if path.is_symlink():
            try:
                if not path.resolve(strict=True).is_relative_to(destination):
                    raise Error(
                        "Patch source symlinks must resolve inside the source tree"
                    )
            except (OSError, RuntimeError) as error:
                raise Error(
                    "Patch source contains an invalid symlink"
                ) from error
        elif not path.is_file() and not path.is_dir():
            raise Error("Patch source contains an unsupported file type")
        else:
            path.chmod(path.stat().st_mode | 0o200)
    destination.chmod(destination.stat().st_mode | 0o200)


def patch_source_digest(source):
    from source import tree_digest

    with tempfile.TemporaryDirectory(
        prefix="publicate-patch-source-"
    ) as directory:
        snapshot = Path(directory) / "source"
        copy_source(source, snapshot)
        return tree_digest(snapshot)


def changed_spans(original, updated):
    """Return original and updated byte spans, refining changed line blocks."""
    old_lines, new_lines = original.splitlines(
        keepends=True
    ), updated.splitlines(keepends=True)
    old_offsets, new_offsets = [0], [0]
    for line in old_lines:
        old_offsets.append(old_offsets[-1] + len(line))
    for line in new_lines:
        new_offsets.append(new_offsets[-1] + len(line))
    for kind, a, b, c, d in SequenceMatcher(
        None, old_lines, new_lines
    ).get_opcodes():
        if kind == "equal":
            continue
        if kind != "replace":
            yield old_offsets[a], old_offsets[b], new_offsets[c], new_offsets[d]
            continue
        old = original[old_offsets[a] : old_offsets[b]]
        new = updated[new_offsets[c] : new_offsets[d]]
        if len(old) + len(new) > 16384:
            yield old_offsets[a], old_offsets[b], new_offsets[c], new_offsets[d]
            continue
        for subkind, i, j, k, l in SequenceMatcher(
            None, old, new, autojunk=False
        ).get_opcodes():
            if subkind != "equal":
                yield old_offsets[a] + i, old_offsets[a] + j, new_offsets[
                    c
                ] + k, new_offsets[c] + l


def comment_findings(before, after, cleaned):
    additions = [(c, d) for a, b, c, d in changed_spans(before, after) if c < d]
    removals = [(a, b) for a, b, c, d in changed_spans(after, cleaned) if a < b]
    line_starts = [0] + [i + 1 for i, byte in enumerate(after) if byte == 10]
    lines = set()
    offset = 0
    for a, b in additions:
        while offset < len(removals) and removals[offset][1] <= a:
            offset += 1
        for index in range(offset, len(removals)):
            c, d = removals[index]
            if c >= b:
                break
            start, end = max(a, c), min(b, d)
            if start < end and after[start:end].strip():
                lines.update(
                    range(
                        bisect_right(line_starts, start),
                        bisect_right(line_starts, end - 1) + 1,
                    )
                )
    return sorted(lines)


def require_clean_patches(root, policy, policy_path, selected):
    report = check_patches(root, policy, policy_path, selected=selected)
    if report["status"] != "passed":
        finding = report["findings"][0]
        raise Error(
            f"Patch comment check failed: {finding['patch']}:"
            f"{finding['path']}:{finding['line']}"
        )
    return report


def check_patches(root, policy, policy_path, *, selected=None):
    from source import selection, tree_digest

    series = policy.get("patches", {}).get("series", [])
    if not series:
        raise Error(
            "Declare patches.series with source, source_digest and patches"
        )
    if selected is None:
        selected, _ = selection(root, policy, policy_path)
    git = os.environ.get("PUBLICATE_GIT")
    if not git:
        raise Error("Run the Nix-packaged publicate command")
    findings, reports = [], []
    for group in series:
        with tempfile.TemporaryDirectory(
            prefix="publicate-patches-"
        ) as directory:
            scratch = Path(directory)
            working = scratch / "source"
            copy_source(root / group["source"], working)
            fingerprint = tree_digest(working)
            if fingerprint != group["source_digest"]:
                raise Error(
                    "Patch source digest does not match its declared pin"
                )
            (scratch / "home").mkdir()
            env = {
                "PATH": str(Path(git).parent),
                "HOME": str(scratch / "home"),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_NO_REPLACE_OBJECTS": "1",
                "LANG": "C.UTF-8",
            }
            current_patch = None

            def invoke(*args, data=None):
                result = subprocess.run(
                    [
                        git,
                        "-c",
                        "core.hooksPath=/dev/null",
                        "-C",
                        str(working),
                        *args,
                    ],
                    env=env,
                    input=data,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                if result.returncode:
                    raise Error(
                        "Patch check failed while applying the selected series: "
                        + (current_patch or "source setup")
                    )
                return result.stdout

            invoke("init", "--quiet")
            for name in group["patches"]:
                current_patch = name
                safe_path(name)
                if name not in selected or selected[name].is_symlink():
                    raise Error(
                        f"Patch must be a selected regular export file: {name}"
                    )
                patch = selected[name].read_bytes()
                invoke("add", "--all", "--force")
                invoke(
                    "apply", "--check", "--whitespace=nowarn", "-", data=patch
                )
                invoke("apply", "--whitespace=nowarn", "-", data=patch)
                changes = invoke(
                    "diff",
                    "--name-only",
                    "--no-ext-diff",
                    "--no-textconv",
                    "-z",
                ).split(b"\0")
                new_files = invoke("ls-files", "--others", "-z").split(b"\0")
                new_names = {os.fsdecode(value) for value in new_files if value}
                changed = sorted(
                    {
                        os.fsdecode(value)
                        for value in changes + new_files
                        if value
                    }
                )
                inputs = {}
                transformed = scratch / "cleaned"
                transformed.mkdir()
                for path in changed:
                    safe_path(path)
                    file = working / path
                    if file.is_symlink():
                        raise Error(
                            "Patch checks do not support changed symlinks"
                        )
                    if not file.exists():
                        continue
                    if not file.resolve().is_relative_to(working):
                        raise Error("Patched source escapes its temporary tree")
                    after = file.read_bytes()
                    if b"\0" in after:
                        raise Error(
                            "Patch checks do not support changed binary files"
                        )
                    before = (
                        b"" if path in new_names else invoke("show", ":" + path)
                    )
                    inputs[path] = (before, after)
                    target = transformed / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(after)
                if inputs:
                    options = {
                        "enabled": True,
                        "include": list(inputs),
                        "preserve": policy.get("comments", {}).get(
                            "preserve", []
                        ),
                    }
                    strip_comments(transformed, {"comments": options})
                for path, (before, after) in inputs.items():
                    cleaned = (transformed / path).read_bytes()
                    for line in comment_findings(before, after, cleaned):
                        findings.append(
                            {
                                "patch": name,
                                "path": path,
                                "line": line,
                                "rule": "patch-comment",
                            }
                        )
                if inputs and strip_comments(
                    transformed, {"comments": options}
                ):
                    raise Error(
                        "Patch source comment stripping is not idempotent"
                    )
                shutil.rmtree(transformed)
            reports.append(
                {"sourceDigest": fingerprint, "patches": group["patches"]}
            )
    return {
        "status": "failed" if findings else "passed",
        "series": reports,
        "findings": findings,
        "buildVerification": "not checked",
        "contentReview": "not assessed",
    }
