# Releases and public branch preparation

## Interactive publishing

Use a private `./publicate/publish.sh` as the default human entry point for publication.
The public [template](../templates/publish.sh.in) reads the configured release
and supplies a publication prompt while delegating export, comparison and verified release to Publicate.

Requires Bash, Git, Nix with flakes, and a private policy with
`publish.repository` and `publish.version` configured. Build verification also
requires Linux user/mount namespaces.

Select the release explicitly in `publicate.toml` before running the script:

```toml
[publish]
version = "1.2.3"
version_file = "VERSION"
repository = "https://example.org/team/project.git"
```

`version_file` names an exported plain-text file containing the application's
SemVer, such as `1.2.3`. Declare it to enforce application/release agreement.
Applications should read that same file for their runtime and package version.
The maintainer updates the policy and application version together and decides
whether a change requires a major, minor or patch increment.

For a project with a Publicate app named `publicate`, install the template from
a Publicate checkout, preserving an existing project script:

```sh
cd /path/to/private-project
mkdir -p publicate
if [ ! -e publicate/publish.sh ]; then
  install -m 755 /path/to/publicate/templates/publish.sh.in publicate/publish.sh
fi
./publicate/publish.sh
```

In a development checkout of Publicate, the template source is
`publicate_public/templates/publish.sh.in`; its own private `./publicate/publish.sh` is
already installed. `PUBLICATE_FLAKE` selects a different Publicate app or pinned
tool input; the default is `.#publicate`. See [integration](USAGE.md) for app setup.
The script explicitly supplies the project's `publicate.toml` as its policy,
including when the selected Nix app has an embedded policy default.

Release preparation follows `build.verify` in the project policy, defaulting to
true. Set it to false for source-only release checks; private run records report
`buildVerification = "skipped"`. Run `./publicate/publish.sh --verify-build` to
request build verification explicitly. Verified builds require Linux user/mount
namespaces. Source and metadata checks apply to every release.

The script shows the configured version and export diff, then asks whether to
publish that exact release and push the current private branch. The default
verifies the candidate and preserves local and remote release refs. Version
conflicts fail; select a new version in the policy and application before retrying.
The script neither increments versions nor writes a remembered version file.
An existing `.publicate/publish-version` is ignored and preserved.

The script also scans known releases and suggests the next major, minor and patch
versions before the publication prompt. For a separate scan, use the project's
Publicate flake input or a Publicate checkout as `INPUT`:

```sh
nix run INPUT -- versions
nix run INPUT -- versions --json
```

The scan includes SemVer branches, tags and private reservations from the local
publication repository, plus its origin's branches and tags. Names are sorted by
numeric SemVer precedence. For a highest version of `v1.2.9`, the suggestions are
major `v2.0.0`, minor `v1.3.0`, and patch `v1.2.10`. With no known releases,
suggestions start from the configured version, or `v0.0.0` when none is configured.
Prerelease and build suffixes are recognized; suggestions are ordinary `vX.Y.Z`
versions. The scan preserves release refs, policy and application files. Choose
the appropriate increment yourself and edit the policy and application version;
conflicting release attempts report the same options and stop.

After successful public publication, the script pushes its current private branch
to the same branch name on the private repository's `origin`, using a normal Git
push. Commit the script and project changes to include them in that private push.
Working-tree edits remain local. The public destination comes from the publication
policy; the private destination comes from the private repository's Git remote.
Private push failures stop the script while retaining the completed public release
and its run record. Decline publication to preserve both local and remote
release refs.

Successful public publication also retires older patch snapshots, keeping five
versions per major/minor line and preserving the version selected by `main`.
`PUBLICATE_KEEP_PATCHES` sets the retained count. Retirement runs through
Publicate before the private branch push. Verification without publication
preserves release refs.

Customize the installed script for the project. Publicate automatically excludes
files named `publish.sh` at every directory depth, including explicit remaps.
The project `publicate/` directory also stays private. Its companion
`review.sh` implements the [ticket review entry point](TICKETS.md).
The reusable template is published as `publish.sh.in`. Keep project-specific
scripts and their publication settings in the private repository.

## SemVer snapshots

`release` and `sync` verify independent version snapshots by default. Both read
`[publish] version` from the private policy; `1.2.3` and `v1.2.3` select branch
`v1.2.3`. SemVer prerelease and build suffixes are accepted. An optional
`--version` must agree with the policy. Publicate never selects an increment.

Each version branch contains one parentless commit of the complete verified
export. Applying a release updates `main` to that retained version. A new version
must have strictly greater SemVer precedence than all known local and remote
versions and private reservations, including retired versions. Build metadata does
not increase precedence. Retrying the highest version requires identical source;
older releases cannot select `main` again. Compatibility decisions belong to the
maintainer.

Use two independent repositories and configure the private policy as above.
The public repository must select `main`. Working checkouts require a single
worktree and clean files, including ignored files. A bare repository is supported.
From a Publicate checkout:

```sh
nix run . -- diff /path/to/private /path/to/public
nix run . -- release /path/to/private /path/to/public
```

Review the exported content before publication. `diff` previews the selected
export with repository refs held fixed and build status `not checked`. `release`
exports again, verifies according to the build policy, and creates a candidate
snapshot with status `verified`, keeping release refs and bindings unchanged.
`sync` uses the same lifecycle. `--apply` updates only local public refs;
`--push` applies and publishes the exact configured version branch and `main`
atomically to the public repository's `origin`.

Remote versions are checked when the public repository has an origin, including
verification and local application. Remote access is then required. Publicate
rechecks references after verification and uses expected-value leases for remote
updates. Concurrent changes reject publication. A rejected push can retain a
prepared local snapshot and its run record; retry the same configured release
once the remote state is reconciled.

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
nix run . -- prune /path/to/private /path/to/public --keep-patches 5
```

Add `--apply` to delete the planned local version branches, or `--push` to delete
remote branches and then the corresponding local branches. `--version` is
repeatable; choose explicit versions, `--keep` or `--keep-patches`.
`--keep-patches N` retains up to N snapshots in each major/minor line, counting
the version selected by `main` toward its line's limit.
`--keep N` retains the version
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
version = "1.2.3"
version_file = "VERSION"
```

`version_branches` defaults to true. `push_url` is optional. Omitting positional
repositories selects a managed bare cache under
`$XDG_CACHE_HOME/publicate` or `~/.cache/publicate` and refreshes remote-tracking
refs for comparison while preserving local release branches. Applying pruning explicitly refreshes the cache's local release
branches from the remote first. From the private project, use your Publicate flake input
or checkout as `INPUT`:

```sh
nix run INPUT -- diff
nix run INPUT -- release --push
nix run INPUT -- prune --keep 5
```

Only `--push` changes remote refs. Git publication uses the invoking terminal's
SSH agent and configuration, including the source repository's `core.sshCommand`.
Git's usual precedence applies: `GIT_SSH_COMMAND`, then `core.sshCommand`, then
`GIT_SSH`.
These settings are used at runtime and are not saved in the publication cache.
Nix verification uses its clean worker configuration. The policy and
repository settings are excluded from export. A separately authored public
usage guide can be explicitly remapped to root `AGENTS.md`.

## Legacy tags and linear history

Set `[publish] version_branches = false` explicitly to retain the earlier tag
workflow. `release --version NAME --apply` creates a fixed lightweight tag on the
selected public branch; `sync --apply` accepts unversioned updates to that branch.
Both commands
verify without moving refs when neither `--apply` nor `--push` is given. With
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
