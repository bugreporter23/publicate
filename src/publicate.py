"""Materialize public Git source views and verify them with isolated Nix."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from common import Error, VERSION, write_json
from policy import policy_at
from source import export, selection, tree_digest
from checks import check_candidate
from nix_worker import verify
from git_branch import prepare
from release import release, sync
from git_diff import diff
from remote import repository_for
from versions import prune
from patch_check import check_patches, patch_source_digest
from lint import lint_documents


def main():
    parser = argparse.ArgumentParser(prog="publicate", description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--policy", type=Path, default=Path("publicate.toml"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan", help="list the selected public paths")
    linting = commands.add_parser(
        "lint", help="lint selected public Markdown without building"
    )
    linting.add_argument("--json", action="store_true")
    commands.add_parser(
        "check-patches",
        help="check patch comments against pinned source without building",
    )
    patch_source = commands.add_parser(
        "patch-source", help="compute a patch source tree digest"
    )
    patch_source.add_argument("source", type=Path)
    exporting = commands.add_parser(
        "export", help="materialize a public source view"
    )
    exporting.add_argument("destination", type=Path)
    checking = commands.add_parser(
        "check", help="check candidate paths, inputs and text without building"
    )
    checking.add_argument("candidate", type=Path)
    verifying = commands.add_parser(
        "verify", help="verify an exported public flake"
    )
    verifying.add_argument("candidate", type=Path)
    verifying.add_argument(
        "--fresh",
        action="store_true",
        help="discard the separate Nix store afterward",
    )
    verifying.add_argument(
        "--record",
        type=Path,
        required=True,
        help="verification JSON outside the candidate",
    )
    preparing = commands.add_parser(
        "prepare", help="commit a verified snapshot to a local public branch"
    )
    preparing.add_argument("candidate", type=Path)
    preparing.add_argument(
        "--repository",
        type=Path,
        required=True,
        help="dedicated bare public repository",
    )
    preparing.add_argument("--branch", required=True)
    preparing.add_argument(
        "--record", type=Path, required=True, help="passed verification JSON"
    )
    pruning = commands.add_parser(
        "prune", help="preview or retire SemVer snapshot branches"
    )
    pruning.add_argument("source", type=Path, nargs="?")
    pruning.add_argument("repository", type=Path, nargs="?")
    pruning.add_argument(
        "--version",
        action="append",
        default=[],
        help="version branch to retire; repeatable",
    )
    pruning.add_argument(
        "--keep",
        type=int,
        help="retain N versions, including the version on main",
    )
    pruning.add_argument(
        "--apply", action="store_true", help="apply local branch deletions"
    )
    pruning.add_argument(
        "--push", action="store_true", help="apply and publish branch deletions"
    )
    pruning.add_argument("--json", action="store_true")
    comparing = commands.add_parser(
        "diff",
        help="preview the export against the public branch without building",
    )
    comparing.add_argument(
        "source",
        type=Path,
        nargs="?",
        help="private project; defaults to --project",
    )
    comparing.add_argument(
        "repository",
        type=Path,
        nargs="?",
        help="public Git repo; defaults to publish.repository",
    )
    comparing.add_argument(
        "--json",
        action="store_true",
        help="print changed paths and patch as JSON",
    )
    for name, help_text in (
        ("release", "export, verify and version two local Git repositories"),
        ("sync", "export, verify and update the public branch without a tag"),
    ):
        publishing = commands.add_parser(name, help=help_text)
        publishing.add_argument(
            "source",
            type=Path,
            nargs="?",
            help="private project; defaults to --project",
        )
        publishing.add_argument(
            "repository",
            type=Path,
            nargs="?",
            help="public Git repo; defaults to publish.repository",
        )
        publishing.add_argument(
            "--version",
            required=name == "release",
            help="SemVer snapshot branch, such as v1.2.3",
        )
        publishing.add_argument(
            "--run-dir",
            type=Path,
            help="parent directory for retained publication runs",
        )
        publishing.add_argument("--fresh", action="store_true")
        publishing.add_argument(
            "--push",
            action="store_true",
            help="publish prepared refs to the public repository's origin",
        )
        publishing.add_argument(
            "--json",
            action="store_true",
            help="print the publication record as JSON",
        )
    args = parser.parse_args()
    if args.command == "patch-source":
        print(
            json.dumps(
                {"sourceDigest": patch_source_digest(args.source)}, indent=2
            )
        )
        return 0
    if args.command in {"diff", "sync", "release", "prune"}:
        root = (args.source or args.project).resolve()
        policy_path = (
            args.policy if args.policy.is_absolute() else root / args.policy
        )
        repository = args.repository
        if repository is None:
            repository = repository_for(
                root, policy_at(policy_path).get("publish", {})
            )
        if args.command == "diff":
            report = diff(root, repository, policy_path)
            print(
                json.dumps(report, indent=2) if args.json else report["patch"],
                end="\n" if args.json else "",
            )
            return 0
        if args.command == "prune":
            report = prune(
                root,
                repository.resolve(),
                policy_path,
                versions=args.version,
                keep=args.keep,
                apply=args.apply,
                push=args.push,
            )
            if args.json:
                print(json.dumps(report, indent=2))
            else:
                print(
                    f"{report['status'].capitalize()}: "
                    + (", ".join(report["pruned"]) or "no versions to retire")
                )
                print("Retained: " + ", ".join(report["retained"]))
            return 0
        if args.command == "release":
            report = release(
                root,
                repository,
                args.version,
                policy_path,
                args.run_dir,
                args.fresh,
                args.push,
            )
        else:
            report = sync(
                root,
                repository,
                policy_path,
                args.run_dir,
                args.fresh,
                args.push,
                version=args.version,
            )
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            label = report["version"] or report["branch"]
            print(
                f"{report['status'].capitalize()} {label} in {report['repository']}"
            )
            print(f"Verified export: {report['source']}")
            print(f"Run records: {report['runDirectory']}")
        return 0
    root = args.project.resolve()
    policy_path = (
        args.policy if args.policy.is_absolute() else root / args.policy
    )
    policy = policy_at(policy_path)
    if args.command == "lint":
        report = lint_documents(root, policy, policy_path)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            for finding in report["findings"]:
                print(f"{finding['path']}:{finding['line']}: {finding['rule']}")
            if report["status"] == "passed":
                print(
                    f"Public prose lint passed for {len(report['documents'])} selected documents."
                )
        return 0 if report["status"] == "passed" else 1
    elif args.command == "check-patches":
        report = check_patches(root, policy, policy_path)
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "passed" else 1
    elif args.command == "plan":
        selected, excluded = selection(root, policy, policy_path)
        print(
            json.dumps(
                {"files": sorted(selected), "excludedCount": excluded}, indent=2
            )
        )
    elif args.command == "export":
        report = export(root, args.destination.absolute(), policy, policy_path)
        print(json.dumps(report, indent=2))
    elif args.command == "check":
        candidate = args.candidate.resolve()
        check_candidate(candidate, policy, policy_path)
        print(
            json.dumps(
                {
                    "status": "passed",
                    "sourceDigest": tree_digest(candidate),
                    "checks": ["blackout-paths", "input-pins", "text-rules"],
                    "styleProfile": policy.get("style", {}).get("profile"),
                    "contentReview": "not assessed",
                },
                indent=2,
            )
        )
    elif args.command == "prepare":
        if policy.get("publish", {}).get("version_branches", True):
            raise Error(
                "Use release or sync --version for SemVer snapshots; "
                "prepare requires explicit publish.version_branches = false"
            )
        report = prepare(
            args.candidate.resolve(),
            args.repository.resolve(),
            args.branch,
            args.record.resolve(),
            policy,
            policy_path,
        )
        print(json.dumps(report, indent=2))
    else:
        candidate = args.candidate.resolve()
        record = args.record.resolve()
        if record.is_relative_to(candidate):
            raise Error(
                "Keep verification records outside the public source tree"
            )
        record.parent.mkdir(parents=True, exist_ok=True)
        try:
            report = verify(candidate, policy, args.fresh, policy_path)
        except (
            Error,
            OSError,
            ValueError,
            subprocess.CalledProcessError,
        ) as error:
            write_json(
                record,
                {"version": VERSION, "status": "failed", "error": str(error)},
            )
            raise
        write_json(record, report)
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "passed" else 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (Error, OSError, ValueError, subprocess.CalledProcessError) as error:
        print("publicate: " + str(error), file=sys.stderr)
        sys.exit(1)
