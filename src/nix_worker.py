"""Evaluate and build a candidate using an independent Nix store."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from common import Error, VERSION, canonical, digest, run, write_json
from source import tree_digest
from checks import check_candidate

NIX_SETTINGS = """experimental-features = nix-command flakes
sandbox = true
sandbox-fallback = false
build-users-group =
accept-flake-config = false
allow-import-from-derivation = false
pure-eval = true
restrict-eval = true
allowed-uris = https:// git+https:// github: gitlab: sourcehut:
builders =
substituters = https://cache.nixos.org
netrc-file = /dev/null
access-tokens =
max-jobs = 2
cores = 2
"""


def verify(candidate, policy, fresh, policy_path):
    nix = os.environ.get("PUBLICATE_NIX")
    git = os.environ.get("PUBLICATE_GIT")
    cert = os.environ.get("PUBLICATE_CERT")
    if not nix or not git or not cert:
        raise Error("Run the Nix-packaged publicate command")
    if not candidate.is_dir():
        raise Error("Candidate directory does not exist")
    fingerprint = tree_digest(candidate)
    identity = digest(canonical({"nix": nix, "settings": NIX_SETTINGS}))[:16]
    cache = (
        Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
        / "publicate"
    )
    report = {
        "version": VERSION,
        "sourceDigest": fingerprint,
        "policyDigest": digest(canonical(policy)),
        "nix": nix,
        "styleProfile": policy.get("style", {}).get("profile"),
        "contentReview": "not assessed",
        "hardwareVerification": "not checked",
        "status": "failed",
    }
    with tempfile.TemporaryDirectory(
        prefix="publicate-verification-"
    ) as directory:
        scratch = Path(directory)
        store = (
            scratch / "store"
            if fresh
            else (cache / ("store-" + identity)).resolve()
        )
        marker = store / ".publicate-public-store.json"
        expected = {"format": 1, "identity": identity}
        if store.exists() and any(store.iterdir()):
            if (
                not marker.exists()
                or json.loads(marker.read_text()) != expected
            ):
                raise Error(
                    "Refusing a store not created by this public verifier"
                )
        store.mkdir(parents=True, exist_ok=True)
        write_json(marker, expected)
        home = scratch / "home"
        config = scratch / "config"
        home.mkdir()
        config.mkdir()
        frozen = scratch / "source"
        env = {
            "PATH": os.pathsep.join(
                [str(Path(nix).parent), str(Path(git).parent)]
            ),
            "HOME": str(home),
            "NIX_CONF_DIR": str(config),
            "NIX_USER_CONF_FILES": "",
            "NIX_CONFIG": NIX_SETTINGS,
            "NIX_PATH": "",
            "NIX_SSL_CERT_FILE": cert,
            "SSL_CERT_FILE": cert,
            "XDG_CONFIG_HOME": str(config),
            "XDG_CACHE_HOME": str(store / "downloads"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "LANG": "C.UTF-8",
        }

        def nix_output(*args):
            return run(
                nix,
                "--store",
                str(store),
                *args,
                env=env,
                cwd=frozen,
                stdout=subprocess.PIPE
            ).stdout

        try:
            check_candidate(candidate, policy, policy_path)
            shutil.copytree(candidate, frozen, symlinks=True)
            check_candidate(frozen, policy, policy_path)
            if tree_digest(frozen) != fingerprint:
                raise Error(
                    "Candidate changed while freezing verification input"
                )
            flags = [
                "--no-write-lock-file",
                "--no-update-lock-file",
                "--no-use-registries",
                "--eval-store",
                str(store),
            ]
            report["phase"] = "public inputs"
            metadata = json.loads(
                nix_output(
                    "flake", "metadata", "--json", *flags, "path:" + str(frozen)
                )
            )
            report["resolvedInputs"] = metadata["locks"]
            report["phase"] = "build"
            targets = [
                "path:" + str(frozen) + "#" + p
                for p in policy["build"]["outputs"]
            ]
            args = ["build", "--json", "--no-link", *flags, *targets]
            json.loads(nix_output(*args))
            report["phase"] = "rebuild"
            built = json.loads(nix_output(*args, "--rebuild"))
            report["outputs"] = built
            paths = sorted(
                {path for item in built for path in item["outputs"].values()}
            )
            report["artifacts"] = json.loads(
                nix_output("path-info", "--json", "--json-format", "2", *paths)
            )
            if (
                tree_digest(candidate) != fingerprint
                or tree_digest(frozen) != fingerprint
            ):
                raise Error("Candidate changed during verification")
            report["status"] = "passed"
            report["rebuildComparison"] = "passed"
            report.pop("phase")
        except (
            Error,
            OSError,
            ValueError,
            subprocess.CalledProcessError,
        ) as error:
            report["error"] = str(error)
        report["store"] = "fresh" if fresh else "public-only warm store"
        if not fresh:
            report["storeRoot"] = str(store)
    return report
