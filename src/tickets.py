"""Maintain UUID tickets on an independently rooted private Git branch."""

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit
import uuid

from common import Error, canonical, digest

BRANCH = "publicate/tickets"
REF = "refs/heads/" + BRANCH
BASE = "refs/publicate/tickets-base"
REMOTE = "refs/publicate/tickets-remote"
DISCOVERY = "PUBLICATE.json"


class Git:
    def __init__(self, root):
        self.root = root

    def __call__(self, *args, data=None, check=True, env=None):
        return subprocess.run(
            [
                os.environ.get("PUBLICATE_GIT", "git"),
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "core.autocrlf=false",
                "-C",
                str(self.root),
                *args,
            ],
            input=data,
            text=True,
            stdout=subprocess.PIPE,
            check=check,
            env=env,
        )

    def text(self, *args):
        return self(*args).stdout.strip()

    def tip(self, ref):
        result = self("rev-parse", "--verify", "--quiet", ref, check=False)
        if result.returncode not in (0, 1):
            result.check_returncode()
        return result.stdout.strip() or None


def endpoint(root, policy):
    configured = policy.get("tickets", {}).get("repository")
    if configured:
        return configured
    manifest = root / DISCOVERY
    if manifest.exists() and not policy:
        value = json.loads(manifest.read_text())
        if (
            value.get("schema") != 1
            or value.get("tickets", {}).get("branch") != BRANCH
        ):
            raise Error("Unsupported ticket discovery contract")
        address = value["tickets"].get("repository")
        if not isinstance(address, str) or not address:
            raise Error("Ticket discovery requires a repository")
        return address
    result = Git(root)("config", "--get", "remote.origin.url", check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def discovery(root, policy):
    if not policy.get("tickets", {}).get("advertise", True):
        return None
    address = endpoint(root, policy)
    if not address:
        return None
    parsed = urlsplit(address)
    if re.fullmatch(r"[^/\s@:]+@[^/\s:]+:[^\s]+", address):
        pass
    elif parsed.scheme in {"https", "ssh"} and parsed.hostname:
        if (
            parsed.password
            or parsed.query
            or parsed.fragment
            or (parsed.scheme == "https" and parsed.username)
        ):
            raise Error(
                "Advertised ticket addresses must be credential-free Git URLs"
            )
    else:
        return None
    return {
        "schema": 1,
        "tickets": {
            "repository": address,
            "branch": BRANCH,
            "path": "tickets",
            "format": "publicate-tickets-v1",
        },
    }


def fingerprint(record):
    return digest(
        canonical({key: record[key] for key in ("title", "body", "version")})
    )


def validate(record, name):
    required = {
        "schema",
        "id",
        "fingerprint",
        "title",
        "body",
        "version",
        "status",
    }
    if (
        not isinstance(record, dict)
        or not required <= record.keys()
        or (record.keys() - required - {"resolution", "reviewed_version"})
    ):
        raise Error("Ticket fields do not match publicate-tickets-v1")
    try:
        identifier = uuid.UUID(record["id"])
    except (ValueError, TypeError, AttributeError):
        raise Error("Ticket IDs must be UUIDv4") from None
    if (
        identifier.version != 4
        or str(identifier) != record["id"]
        or name != f"tickets/{identifier}.json"
    ):
        raise Error("Ticket filenames must match their UUIDv4")
    if (
        type(record["schema"]) is not int
        or record["schema"] != 1
        or not isinstance(record["status"], str)
        or record["status"] not in {"open", "applied", "inapplicable"}
    ):
        raise Error("Unsupported ticket schema or status")
    if (
        any(
            not isinstance(record.get(key, ""), str)
            for key in (
                "title",
                "body",
                "version",
                "resolution",
                "reviewed_version",
            )
        )
        or not record["title"].strip()
        or not record["body"].strip()
    ):
        raise Error("Tickets require a title, body and string context fields")
    if record["fingerprint"] != fingerprint(record):
        raise Error("Ticket immutable fields differ from their fingerprint")
    if record["status"] != "open" and not record.get("resolution", "").strip():
        raise Error("Resolved tickets require a resolution")
    return record


def records_at(git, commit):
    if not commit:
        return {}
    if len(git.text("rev-list", "--parents", "-n", "1", commit).split()) != 1:
        raise Error("Ticket branches must contain one parentless snapshot")
    result = {}
    for entry in git("ls-tree", "-rz", commit).stdout.split("\0"):
        if not entry:
            continue
        info, name = entry.split("\t", 1)
        mode, kind, oid = info.split()
        if (
            mode != "100644"
            or kind != "blob"
            or not re.fullmatch(r"tickets/[0-9a-f-]{36}\.json", name)
        ):
            raise Error(
                "Ticket snapshots contain only regular UUID JSON records"
            )
        record = validate(json.loads(git("cat-file", "blob", oid).stdout), name)
        result[record["id"]] = record
    return result


def merge(base, local, remote):
    result = {}
    for identifier in base.keys() | local.keys() | remote.keys():
        before, ours, theirs = (
            base.get(identifier),
            local.get(identifier),
            remote.get(identifier),
        )
        identities = {
            record["fingerprint"] for record in (before, ours, theirs) if record
        }
        if len(identities) > 1:
            raise Error(f"Ticket identity fields are immutable: {identifier}")
        if ours == before:
            chosen = theirs
        elif theirs == before or ours == theirs:
            chosen = ours
        else:
            raise Error(f"Concurrent ticket edits conflict: {identifier}")
        if chosen is not None:
            result[identifier] = chosen
    return result


def coalesce(records, remote):
    preferred = {
        record["fingerprint"]: identifier
        for identifier, record in remote.items()
    }
    result = {}
    groups = {}
    for identifier, record in records.items():
        groups.setdefault(record["fingerprint"], []).append(identifier)
    for fingerprint_value, identifiers in groups.items():
        chosen = preferred.get(fingerprint_value)
        if chosen not in identifiers:
            chosen = min(identifiers)
        for identifier in identifiers:
            if identifier == chosen:
                continue
            left, right = dict(records[identifier]), dict(records[chosen])
            left.pop("id")
            right.pop("id")
            if left != right:
                raise Error(
                    "Duplicate ticket content has conflicting review states"
                )
        result[chosen] = records[chosen]
    return result


def commit_records(git, records, directory):
    with tempfile.TemporaryDirectory(
        prefix="publicate-ticket-index-", dir=directory
    ) as temporary:
        env = dict(
            os.environ,
            GIT_INDEX_FILE=str(Path(temporary) / "index"),
            GIT_AUTHOR_NAME="user.name",
            GIT_AUTHOR_EMAIL="user.email",
            GIT_COMMITTER_NAME="user.name",
            GIT_COMMITTER_EMAIL="user.email",
            GIT_AUTHOR_DATE="@0 +0000",
            GIT_COMMITTER_DATE="@0 +0000",
            GIT_NO_REPLACE_OBJECTS="1",
        )
        git("read-tree", "--empty", env=env)
        entries = []
        for identifier, record in sorted(records.items()):
            name = f"tickets/{identifier}.json"
            validate(record, name)
            blob = git(
                "hash-object",
                "-w",
                "--stdin",
                data=canonical(record).decode() + "\n",
                env=env,
            ).stdout.strip()
            entries.append(f"100644 {blob}\t{name}\0")
        git(
            "update-index", "-z", "--index-info", data="".join(entries), env=env
        )
        tree = git("write-tree", env=env).stdout.strip()
        return git(
            "-c",
            "commit.gpgSign=false",
            "-c",
            "i18n.commitEncoding=UTF-8",
            "commit-tree",
            tree,
            "-m",
            "publicate",
            env=env,
        ).stdout.strip()


@contextmanager
def queue_lock(git):
    directory = Path(
        git.text("rev-parse", "--path-format=absolute", "--git-common-dir")
    )
    with (directory / "publicate-tickets.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield directory


def fetch_tip(git, address):
    listing = git("ls-remote", "--heads", address, REF).stdout.strip()
    if not listing:
        return None
    git("fetch", "--no-tags", address, f"+{REF}:{REMOTE}")
    return git.tip(REMOTE)


def update(root, policy, transform, *, push=False, fetch=False):
    git = Git(root)
    address = endpoint(root, policy) if push or fetch else None
    if (push or fetch) and not address:
        raise Error("Set tickets.repository or configure the private origin")
    with queue_lock(git) as directory:
        if (
            f"branch {REF}"
            in git.text("worktree", "list", "--porcelain").splitlines()
        ):
            raise Error(
                "Ticket queue updates require detached review worktrees"
            )
        current = git.tip(REF)
        base = git.tip(BASE)
        remote = fetch_tip(git, address) if push or fetch else base
        records = merge(
            records_at(git, base),
            records_at(git, current),
            records_at(git, remote),
        )
        records = transform(records)
        for attempt in range(3):
            records = coalesce(records, records_at(git, remote))
            commit = commit_records(git, records, directory)
            if push:
                result = git(
                    "push",
                    "--no-follow-tags",
                    "--signed=false",
                    f"--force-with-lease={REF}:{remote or ''}",
                    address,
                    f"{commit}:{REF}",
                    check=False,
                )
                if result.returncode:
                    latest = fetch_tip(git, address)
                    if latest == remote or attempt == 2:
                        result.check_returncode()
                    records = merge(
                        records_at(git, remote),
                        records,
                        records_at(git, latest),
                    )
                    remote = latest
                    continue
            zero = "0" * len(commit)
            git("update-ref", REF, commit, current or zero)
            if push or fetch:
                if push or remote:
                    git("update-ref", BASE, commit if push else remote)
                elif base:
                    git("update-ref", "-d", BASE, base)
            return {
                "status": "published" if push else "prepared",
                "branch": BRANCH,
                "commit": commit,
                "tickets": len(records),
            }


def create(root, policy, title, body, version="", *, push=False):
    draft = {
        "schema": 1,
        "title": title.strip(),
        "body": body.strip(),
        "version": version,
        "status": "open",
    }
    draft["fingerprint"] = fingerprint(draft)
    identifier = None

    def insert(records):
        nonlocal identifier
        existing = next(
            (
                r
                for r in records.values()
                if r["fingerprint"] == draft["fingerprint"]
            ),
            None,
        )
        identifier = existing["id"] if existing else str(uuid.uuid4())
        if not existing:
            records[identifier] = dict(draft, id=identifier)
        return records

    result = update(root, policy, insert, push=push)
    identifier = next(
        record["id"]
        for record in records_at(Git(root), result["commit"]).values()
        if record["fingerprint"] == draft["fingerprint"]
    )
    return dict(result, id=identifier, path=f"tickets/{identifier}.json")
