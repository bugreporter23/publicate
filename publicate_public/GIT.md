# Releases and public branch preparation

## Interactive publishing

Use a private `./publish.sh` as the default human entry point for publication.
The public [template](../templates/publish.sh.in) supplies version and publication
prompts while delegating export, comparison and verified release to Publicate.

Requires Bash, Git, Nix with flakes, Linux user/mount namespaces, and a private
`publicate.toml` with `publish.repository` configured as described below. For a
project with a Publicate app named `publicate`, install the template from a
Publicate checkout, preserving an existing project script:

```sh
cd /path/to/private-project
if [ ! -e publish.sh ]; then
  install -m 755 /path/to/publicate/templates/publish.sh.in publish.sh
fi
./publish.sh
```

In a development checkout of Publicate, the template source is
`publicate_public/templates/publish.sh.in`; its own private `./publish.sh` is
already installed. `PUBLICATE_FLAKE` selects a different Publicate app or pinned
tool input; the default is `.#publicate`. See [integration](USAGE.md) for app setup.

The script shows the export diff, asks whether to bump the version, and accepts
an exact new SemVer branch when requested. First use selects `v0.1.0`; subsequent
runs remember the last successful version privately in
`.publicate/publish-version`. Keeping a version retries its fixed snapshot;
changed content requires a new version. The final prompt chooses publication to
`origin` or local preparation. Release performs build verification in either case.
A failed operation stops the script and preserves its previous remembered version.

Customize the installed script for the project. Publicate automatically excludes
files named `publish.sh` at every directory depth, including explicit remaps.
The reusable template is published as `publish.sh.in`. Keep project-specific
scripts and their publication settings in the private repository.

## SemVer snapshots

`release` and `sync` publish independent version snapshots by default. Supply
`--version vMAJOR.MINOR.PATCH`; SemVer prerelease and build suffixes are accepted.
Each version branch contains one parentless commit of the complete verified
export. `main` selects the release from the last successful operation. Release
identities are version branches. An unchanged retry keeps the same commit; changed source requires
a different version. SemVer compatibility decisions belong to the publisher.

Use two independent repositories. The public repository must select `main`.
Working checkouts require a single worktree and clean files, including ignored
files. A bare repository is also supported. From the Publicate checkout:

```sh
nix run . -- diff /path/to/private /path/to/public
nix run . -- release /path/to/private /path/to/public --version v1.2.3
```

Review the exported content before publication. `diff` previews the exact selected
export with repository refs held fixed and build status `not checked`. `release` exports again,
verifies the build, and prepares the snapshot. `sync --version v1.2.3` uses the
same snapshot lifecycle. Add `--push` only to publish the version branch and
`main` atomically to the public repository's `origin`. Push checks expected values for updated remote refs observed before verification;
a concurrent update to those refs rejects the push.
A rejected push can leave a prepared local snapshot and its verification record.

Each run retains fresh `source/`, `verification.json` and `release.json` files
outside both repositories. `--run-dir DIRECTORY` selects their parent; the default
is under `$XDG_STATE_HOME/publicate` or `~/.local/state/publicate`. Only a passed
verification record for the exact tree and policy permits snapshot preparation.

Author and committer are `user.name` / `user.email`, timestamps are the Unix epoch,
and the entire commit message is `publicate`. Publication commits contain the
exported tree and fixed metadata. Git trees are built with a temporary index and fixed file bytes;
removed files and file/directory transitions are represented in each snapshot.
File filters and hooks are disabled during snapshot construction. Empty
directories are rejected by snapshot preparation.

## Retire versions

Preview explicit retirement or a sliding window:

```sh
nix run . -- prune /path/to/private /path/to/public --version v1.2.0
nix run . -- prune /path/to/private /path/to/public --keep 5
```

Add `--apply` to delete the planned local version branches, or `--push` to delete
remote branches and then the corresponding local branches. `--version` is
repeatable; choose either explicit versions or `--keep`. `--keep N` retains the version
selected by `main` plus the highest remaining versions by SemVer precedence,
up to N total. Build metadata breaks precedence ties by branch name. The version
selected by `main` stays retained. A same-named tag is retired with its branch
when it points to the same snapshot; a conflicting tag stops retirement. Branches
and tags with other names are untouched.

With versions 1 through 6 published, retiring version 1 leaves versions 2 through
6 visible to a new ordinary clone. Retained commit IDs stay fixed because each
snapshot is parentless. Retirement changes advertised refs; server storage follows
Git garbage collection and retention.

Publicate keeps a private version binding and retirement ledger inside the local
public Git directory. The ledger reserves retired names and keeps live version
bindings fixed. Preserve `publicate-versions.json` from the Git directory when
moving the publication workspace. Ordinary Git clones transfer public refs and
objects. Consumers should retain required source and pin its resolved commit and
content hash; the publisher controls availability of retired releases.

## Configured repository

Set the public Git URL privately in `publicate.toml`:

```toml
[publish]
repository = "https://example.org/team/project.git"
push_url = "git@example.org:team/project.git"
version_branches = true
```

`version_branches` defaults to true. `push_url` is optional. Omitting positional
repositories selects a managed bare cache under
`$XDG_CACHE_HOME/publicate` or `~/.cache/publicate` and refreshes its public branch
view from the remote. From the private project, use your Publicate flake input
or checkout as `INPUT`:

```sh
nix run INPUT -- diff
nix run INPUT -- release --version v1.2.3 --push
nix run INPUT -- prune --keep 5
```

Only `--push` changes remote refs. Git publication uses the invoking terminal's
SSH agent and configuration. Nix verification uses its clean worker configuration. The policy and
repository settings are excluded from export. A separately authored public
usage guide can be explicitly remapped to root `AGENTS.md`.

## Legacy tags and linear history

Set `[publish] version_branches = false` explicitly to retain the earlier tag
workflow. `release --version NAME` creates a fixed lightweight tag on the selected
public branch; `sync` accepts unversioned updates to that branch. With
`replace_main = false`, new commits retain public ancestry. With `replace_main = true`,
`main` is replaced by a parentless snapshot while existing tags remain fixed.
The SemVer branch pruning command requires `version_branches = true`.

The lower-level `prepare` command accepts an exported candidate and its passed
verification record. In legacy mode it updates the supplied local branch:

```sh
nix run . -- prepare /path/to/export --repository /path/to/public.git --branch main --record /path/to/verification.json
```

The repository must be bare and independent of the private source. Existing
public ancestry must already be suitable for publication. Use `release` or
`sync` for the SemVer snapshot lifecycle.
