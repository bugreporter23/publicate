"""Select and materialize tracked source, without Git history."""

import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile

from common import Error, blocked, canonical, digest, safe_path
from policy import matches
from checks import style_check
from comments import strip_comments
from tickets import DISCOVERY, discovery


def policy_source(source, policy_path):
    try:
        return source.resolve() == policy_path.resolve() or source.samefile(
            policy_path
        )
    except (OSError, RuntimeError):
        return False


def source_parents(source, root):
    for parent in source.relative_to(root).parents:
        if (root / parent).is_symlink():
            raise Error(
                f"Source path traverses a symlink: {source.relative_to(root)}"
            )


def tracked(root, policy_path, prefix="", include=("*",), exclude=()):
    records = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "--stage", "-z"]
    )
    for record in records.split(b"\0"):
        if not record:
            continue
        info, raw_path = record.split(b"\t", 1)
        mode, _, stage = info.decode().split()
        name = os.fsdecode(raw_path)
        safe_path(name)
        full = prefix + name
        if blocked(full, policy_path) or matches(full, exclude):
            continue
        if policy_source(root / name, policy_path):
            continue
        if stage != "0":
            if not matches(full, include):
                continue
            raise Error(
                f"Resolve Git conflicts before exporting: {prefix + name}"
            )
        if mode == "160000":
            if not any(
                matches(full, [p])
                or p.startswith(full + "/")
                or any(c in p for c in "*?[")
                for p in include
            ):
                continue
            child = root / name
            source_parents(child, root)
            if child.is_symlink() or not child.resolve().is_relative_to(
                root.resolve()
            ):
                raise Error(
                    f"Submodule root must be a real in-tree directory: {full}"
                )
            if not (child / ".git").exists():
                raise Error(
                    f"Initialize the selected submodule before exporting: {prefix + name}"
                )
            yield from tracked(
                child, policy_path, prefix + name + "/", include, exclude
            )
        else:
            source = root / name
            if source.exists() or source.is_symlink():
                yield prefix + name, source


def tree_digest(root):
    entries = []
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            entries.append([name, "symlink", os.readlink(path)])
        elif path.is_file():
            entries.append(
                [
                    name,
                    "executable" if path.stat().st_mode & 0o111 else "file",
                    digest(path.read_bytes()),
                ]
            )
        elif path.is_dir():
            entries.append([name, "directory"])
    return digest(canonical(entries))


def selection(root, policy, policy_path):
    options = policy["export"]
    files = dict(
        tracked(
            root,
            policy_path,
            include=options["include"] + list(options.get("files", {})),
            exclude=options.get("exclude", []),
        )
    )
    selected = {
        name: source
        for name, source in files.items()
        if not blocked(name, policy_path)
        and name != ".gitmodules"
        and matches(name, options["include"])
        and not matches(name, options.get("exclude", []))
    }
    destinations = set()
    for source, destination in options.get("files", {}).items():
        safe_path(source)
        safe_path(destination)
        if blocked(source, policy_path) or blocked(
            destination, policy_path, public_agents=True
        ):
            raise Error(
                f"Remapping cannot include blacked-out material: {source}"
            )
        if source not in files:
            raise Error(f"Remapped source must be Git-tracked: {source}")
        if destination in destinations:
            raise Error(f"Duplicate remapped destination: {destination}")
        destinations.add(destination)
        selected.pop(source, None)
        selected[destination] = files[source]
    for name, source in selected.items():
        path = safe_path(name)
        if path.as_posix() != name:
            raise Error(f"Export destination must be normalized: {name}")
        if any(parent.as_posix() in selected for parent in path.parents):
            raise Error(f"Export file/directory conflict: {name}")
        source_parents(source, root)
    if "flake.nix" not in selected or "flake.lock" not in selected:
        raise Error("The public view must contain flake.nix and flake.lock")
    return selected, len(files) - len(selected)


def export(root, destination, policy, policy_path):
    root = root.resolve()
    destination = destination.resolve()
    if destination == root or destination.is_relative_to(root):
        raise Error("Export outside the development checkout")
    if destination.exists() and (
        not destination.is_dir() or any(destination.iterdir())
    ):
        raise Error("Export destination must be absent or empty")
    selected, excluded = selection(root, policy, policy_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".publicate-", dir=destination.parent
    ) as directory:
        stage = Path(directory)
        for name, source in sorted(selected.items()):
            target = stage / name
            if any(
                parent.is_symlink()
                for parent in target.parents
                if parent != stage
            ):
                raise Error(f"Cannot write through a symlink parent: {name}")
            if source.is_symlink():
                link = os.readlink(source)
                if PurePosixPath(link).is_absolute():
                    raise Error(f"Absolute symlink is not exportable: {name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(link)
            else:
                if not source.is_file():
                    raise Error(f"Tracked file is unavailable: {name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
                target.chmod(0o755 if source.stat().st_mode & 0o111 else 0o644)
        for name in selected:
            target = stage / name
            try:
                if not target.resolve(strict=True).is_relative_to(stage):
                    raise Error(f"Symlink escapes the public view: {name}")
            except (OSError, RuntimeError) as error:
                raise Error(
                    f"Symlink requires excluded or missing material: {name}"
                ) from error
        stripped = strip_comments(stage, policy)
        channel = discovery(root, policy)
        if channel is not None:
            if (stage / DISCOVERY).exists() or (stage / DISCOVERY).is_symlink():
                raise Error(
                    "PUBLICATE.json is reserved for generated ticket discovery"
                )
            (stage / DISCOVERY).write_bytes(canonical(channel) + b"\n")
        patch_report = None
        if policy.get("patches", {}).get("series"):
            from patch_check import require_clean_patches

            patch_report = require_clean_patches(
                stage,
                policy,
                policy_path,
                {name: stage / name for name in selected},
            )
        style_check(stage, policy)
        fingerprint = tree_digest(stage)
        if destination.exists():
            destination.rmdir()
        stage.rename(destination)
    return {
        "sourceDigest": fingerprint,
        "files": sorted(
            [*selected, *([DISCOVERY] if channel is not None else [])]
        ),
        "excludedCount": excluded,
        "commentsStripped": stripped,
        "patchChecks": patch_report,
        "patchesUnchecked": sorted(
            name
            for name in selected
            if Path(name).suffix.lower() in {".patch", ".diff"}
            and name
            not in {
                patch
                for group in policy.get("patches", {}).get("series", [])
                for patch in group["patches"]
            }
        ),
    }
