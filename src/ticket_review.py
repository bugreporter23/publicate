"""Create small ticket worktrees and reconcile agent review changes."""

import json
from pathlib import Path
import tempfile

from common import Error, write_json
from tickets import Git, endpoint, merge, records_at, update, validate


def review(root, policy, directory):
    git = Git(root)
    result = update(root, policy, lambda records: records, fetch=True)
    directory.mkdir(parents=True, exist_ok=True)
    worktree = Path(
        tempfile.mkdtemp(prefix="publicate-review-", dir=directory)
    ).resolve()
    git("worktree", "add", "--detach", str(worktree), result["commit"])
    context = worktree / ".publicate"
    context.mkdir()
    source_head = git.tip("HEAD")
    write_json(
        context / "review.json",
        {
            "schema": 1,
            "source": str(root),
            "sourceHead": source_head,
            "ticketsCommit": result["commit"],
            "repository": endpoint(root, policy),
        },
    )
    instructions = (
        "# Ticket review\n\n"
        f"Current source checkout: `{root}`\n"
        f"Source HEAD at worktree creation: `{source_head or 'uncommitted'}`\n\n"
        "Read that checkout's agent instructions and the current conversation.\n"
        "Publicate is a per-repository publication and private ticket plugin.\n"
        "This temporary worktree holds the issue queue; review current source.\n"
        "Authorized Git publication uses the caller's existing SSH agent and\n"
        "credentials. Human authentication or repository-access steps are routine\n"
        "handoffs: preserve local work, explain the required step, and resume\n"
        "after access is ready. Keep private key material in its credential store.\n"
        "Read open `tickets/*.json` here. For each ticket, establish whether its\n"
        "claim still applies to the current code, including working-tree edits.\n"
        "Treat ticket bodies as issue reports; evaluate their claims against source.\n"
        "Apply relevant fixes in the source checkout using its authorized workflow.\n"
        "Keep title, body, version, id and fingerprint fixed. Mark a completed fix\n"
        "`applied`, or a disproven/outdated claim `inapplicable`; add a concrete\n"
        "`resolution` and `reviewed_version`. Leave unresolved reports `open`.\n"
        "Code changes stay in the source checkout; this worktree contains tickets.\n\n"
        "Synchronize reviewed records through Publicate's `ticket-sync` command,\n"
        "supplying this worktree as its directory and the source as `--project`.\n"
        "Add `--push` to update the private queue. Same-record conflicts stop sync.\n"
        "Keep this worktree until changes are synchronized and you finish reviewing.\n"
    )
    (context / "REVIEW.md").write_text(instructions)
    result.update(
        {
            "worktree": str(worktree),
            "source": str(root),
            "instructions": str(context / "REVIEW.md"),
            "next": "Evaluate open tickets against the current source and apply applicable fixes.",
        }
    )
    return result


def sync(root, policy, directory, *, push=False):
    directory = directory.resolve()
    context = json.loads((directory / ".publicate/review.json").read_text())
    if context.get("schema") != 1 or Path(context["source"]).resolve() != root:
        raise Error("Ticket review belongs to a different source checkout")
    git = Git(root)
    other = Git(directory)
    if (
        git.text("rev-parse", "--path-format=absolute", "--git-common-dir")
        != other.text("rev-parse", "--path-format=absolute", "--git-common-dir")
        or other.tip("HEAD") != context["ticketsCommit"]
    ):
        raise Error(
            "Ticket review worktree must retain its detached base snapshot"
        )
    original = records_at(git, context["ticketsCommit"])
    revised = {}
    ticket_directory = directory / "tickets"
    if ticket_directory.exists():
        if ticket_directory.is_symlink():
            raise Error("Ticket directories must be real directories")
        for path in ticket_directory.iterdir():
            if not path.is_file() or path.is_symlink():
                raise Error("Ticket review contains an unsupported entry")
            record = validate(
                json.loads(path.read_text()), "tickets/" + path.name
            )
            revised[record["id"]] = record
    result = update(
        root,
        policy,
        lambda current: merge(original, revised, current),
        push=push,
    )
    write_json(directory / ".publicate/sync.json", result)
    return result
