# Verification contract

Export materializes the selected working-tree files before Nix evaluation.
Verification freezes a private copy for the complete evaluation/build sequence.
Git history and internal agent instructions are excluded. Tests follow the project's
explicit selection policy, including ordinary inline tests. The policy selects and
remaps paths; content review assesses personal information in selected bytes.
The selected, transformed bytes determine the public tree identity.
The active policy is also excluded. Destination prefix conflicts are rejected
before copying; source parents must be real directories inside the project.
Default comment stripping changes supported source before text checks, digests and
verification. Retained docstrings and notices remain subject to content review.

Export verification covers declared outputs of the exported tree. Private-only
files, tests and build steps need their own appropriate checks when changed.
Publication rules do not require a particular source layout or test mechanism.

Verification uses packaged Nix/Git, empty configuration and home directories,
pure/restricted evaluation, HTTPS/public forge inputs, and a separate local
chroot store. Build sandboxing is mandatory. Public fetches and signed public
substitutes supply the verification store and its dependencies.

Each declared output is built and rebuilt for comparison. Declare changed
libraries separately from wrappers. The external record includes source/policy
digests, resolved inputs and artifact hashes.
`check` exposes path/input/text checks separately; content review is explicitly
reported as `not assessed`. See the [source guidance](STYLE.md) for opt-in text rules.

This establishes build independence under these settings. Use trusted evaluation
inputs. Source disclosure, fetcher behavior, runtime and hardware compatibility,
and complete toolchain reproducibility require their own review and evidence.
The warm-store marker identifies the runner configuration; source provenance and
cache integrity require separate verification.
