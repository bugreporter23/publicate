# Publicate

Export selected Git source into a standalone Nix project and verify its declared
build outputs using a separate store.

Requires Nix with flakes. Build verification also requires Linux user/mount
namespaces. Build with `nix build`; run with `nix run . -- --help`.

See [usage](publicate_public/USAGE.md) and the [verification contract](publicate_public/DESIGN.md).
Agent consumers should follow the [public source guidance](publicate_public/STYLE.md).
Verified exports support [local branch preparation](publicate_public/GIT.md).

For human publishing, use a private `./publicate/publish.sh` based on the public
[template](templates/publish.sh.in). The recommended
[interactive workflow](publicate_public/GIT.md#interactive-publishing) previews
the configured version and export, then asks about publication. Project scripts
named `publish.sh` are automatically excluded from export.

The [private ticket backchannel](publicate_public/TICKETS.md) gives agents a
UUID-based issue format and a tickets-only Git branch. Exported `PUBLICATE.json`
advertises the private repository address for authorized contributors.
`publicate/review.sh` prepares a small ticket worktree for an existing agent to
evaluate against the current source.

For two existing local repositories, configure `[publish] version` in the private
policy and declare `version_file` for an exported application version file:

```sh
nix run . -- release /path/to/private /path/to/public
```

The default verifies the candidate and preserves release refs. Add `--apply` to
update local refs or `--push` to publish to the public repository's `origin` after
verification.

Pin Publicate and published dependencies to specific commits and content hashes
in your Nix lockfile. Independent SemVer branches name releases and can be retired explicitly.

[Design through integration](publicate_public/INTEGRATION-BASED-DESIGN.md) describes
the relationship between exploratory integration and independent component releases.
