"""Strip comments from staged source with the packaged Uncomment tool."""

import json
import os
from pathlib import Path
import subprocess
import tempfile

from common import Error
from policy import matches


PRESERVE = [
    "SPDX-",
    "Copyright",
    "copyright",
    "COPYRIGHT",
    "License",
    "license",
    "LICENSE",
    "coding:",
    "coding=",
    "go:",
    "+build",
    "//line ",
    "type:",
    "noqa",
    "pragma:",
    "@ts-",
    "/// <reference",
    "sourceMappingURL=",
    "sourceURL=",
    "frozen_string_literal:",
]


def strip_comments(stage, policy):
    options = policy.get("comments", {})
    if not options.get("enabled", True):
        return []
    command = os.environ.get("PUBLICATE_UNCOMMENT")
    if not command:
        raise Error(
            "Run the Nix-packaged publicate command for comment stripping"
        )
    files = [
        path
        for path in sorted(stage.rglob("*"))
        if path.is_file()
        and not path.is_symlink()
        and (
            "include" not in options
            or matches(path.relative_to(stage).as_posix(), options["include"])
        )
    ]
    if not files:
        if "include" in options:
            raise Error("Comment stripping matched no regular export files")
        return []
    with tempfile.TemporaryDirectory(prefix="publicate-comments-") as directory:
        scratch = Path(directory)
        config = scratch / "uncomment.toml"
        patterns = PRESERVE + options.get("preserve", [])
        config.write_text(
            "[global]\nremove_todos = true\nremove_fixme = true\n"
            + "remove_docs = true\nuse_default_ignores = false\nrespect_gitignore = false\n"
            + "preserve_patterns = "
            + json.dumps(patterns)
            + "\n"
            + '\n[languages.python]\nname = "python"\n'
            + 'extensions = ["py", "pyw", "pyi", "pyx", "pxd"]\n'
            + 'comment_nodes = ["comment"]\n'
        )
        env = {
            "PATH": str(Path(command).parent),
            "HOME": str(scratch),
            "XDG_CONFIG_HOME": str(scratch),
            "LANG": "C.UTF-8",
        }
        before = {path: path.read_bytes() for path in files}
        result = subprocess.run(
            [
                command,
                "--config",
                str(config),
                "--no-default-ignores",
                "--remove-todo",
                "--remove-fixme",
                "--no-gitignore",
                "--",
                *(str(path) for path in files),
            ],
            cwd=scratch,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        errors = ["Error processing"]
        if "include" in options:
            errors.extend(["Skipping ", "No supported files"])
        if result.returncode or any(
            message in result.stderr for message in errors
        ):
            raise Error("Comment stripping failed for selected export files")
        return [
            path.relative_to(stage).as_posix()
            for path in files
            if path.read_bytes() != before[path]
        ]
