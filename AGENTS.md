# Using Publicate as an agent

Publicate supplies two repository-level services: verified public source snapshots
and a private ticket plugin. Each project owns its source, queue and access rules.
Use the advertised endpoint to report findings, and evaluate queued reports against
the project's current code. Publicate's own development uses these same contracts.

Edit the private project's source and export policy. Public checkouts are generated
outputs; use Publicate to construct and update them.

Use the [private ticket backchannel](TICKETS.md) to report issues in exported
source. Read `PUBLICATE.json` for the private endpoint and use `ticket --push`
with authorized Git credentials. In a source project, `publicate/review.sh`
prepares a tickets-only worktree for your existing agent session. Read its
generated instructions, check open tickets against current code, apply relevant
fixes in the source checkout, and use `ticket-sync --push` for review records.
Review worktrees default to the system temporary directory; pass a directory
explicitly when another location suits the task. They hold ticket records and
share Git objects with the source checkout.

Authorized ticket publication is ordinary Git work using the caller's existing
SSH agent and credentials. An SSH unlock, host verification or repository-access
request is a routine human handoff. Preserve the local ticket or review, explain
the exact authentication step, and retry after access is ready. Existing task
authorization covers the requested push. Keep private key material in its
credential store; use the established authentication flow. Successful ticket
submission requires queue write access, while source publication follows the
project's separate release authorization.

Use two independent local Git repositories and a clean public checkout:

```sh
publicate diff /path/to/private /path/to/public
publicate sync /path/to/private /path/to/public --version v1.2.3
```

`diff` previews additions, modifications and deletions with repository refs held
fixed and build status `not checked`. Review the exported content for disclosure. `sync` exports
again, verifies the build and prepares an independent SemVer snapshot branch.
`release --version v1.2.3` uses the same lifecycle. Add `--push` only when
publication is authorized; preparation otherwise remains local.

- Use Publicate's comparison and preparation commands. If an operation is missing,
  extend Publicate and keep publication within its verified workflow.
- Write documentation for consumers. Useful explanations, examples, test guidance
  and required attribution belong in public docs; personal session records stay private.
- Use synthetic examples and neutral diagnostics. Follow the selected public
  source style rules; disclosure approval requires content review.
- Comment stripping is enabled by default. Review retained docstrings, directives
  and notices; add preservation exceptions only for a concrete requirement.
- Pin Publicate and published inputs to resolved commits and content hashes;
  publish exact SemVer branches and retain the versions consumers need.
  Use `prune` to preview retirement, then `--apply` or an authorized `--push`.
- Stop on export or verification failure. Use the successful run's export
  and record. Preserve existing artifacts and private development history.

Patch files retain their original bytes during export. Declare a pinned source and ordered
series, then run `check-patches` to report introduced removable comment text
through temporary source application and stripping comparisons. Declared series are also checked during
export and candidate verification. See [usage](USAGE.md).

## Preserve working code and tests

Tests are ordinary source. Publish inline or separate tests when selected by the
project's policy. Publicate does not require moving tests, removing upstream tests,
concatenating source, or concealing ordinary test declarations. Keep working source
and test layouts unless the publisher specifically requests a change.

When some tests genuinely need to remain private, exclude their paths explicitly
and use the project's supported language and build mechanisms. Validate any changed
private build separately from the exported build. A successful export build says
nothing about excluded private files or private-only build steps. A byte comparison
is useful evidence about bytes; it does not verify that the changed build works.
Report checks actually run and respect the user's testing and build constraints.
