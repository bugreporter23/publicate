# Publicate

Export selected Git source into a standalone Nix project and verify its declared
build outputs using a separate store.

Requires Linux user/mount namespaces and Nix with flakes. Build with `nix build`;
run with `nix run . -- --help`.

See [usage](publicate_public/USAGE.md) and the [verification contract](publicate_public/DESIGN.md).
Agent consumers should follow the [public source guidance](publicate_public/STYLE.md).
Verified exports support [local branch preparation](publicate_public/GIT.md).

For human publishing, use a private `./publish.sh` based on the public
[template](templates/publish.sh.in). The recommended
[interactive workflow](publicate_public/GIT.md#interactive-publishing) previews
the export and asks about the version and publication. Project scripts named
`publish.sh` are automatically excluded from export.

For two existing local repositories:

```sh
nix run . -- release /path/to/private /path/to/public --version v0.1.0
```

Add `--push` to publish to the public repository's `origin` after verification.

Pin Publicate and published dependencies to specific commits and content hashes
in your Nix lockfile. Independent SemVer branches name releases and can be retired explicitly.

[Design through integration](publicate_public/INTEGRATION-BASED-DESIGN.md) describes
the relationship between exploratory integration and independent component releases.
