# Usage

Create `publicate.toml` in the project being exported. Selected sources must be
Git-tracked; the working-tree contents are exported.

```toml
version = 1
[export]
include = ["flake.nix", "flake.lock", "src", "nix", "publicate_public"]
[export.files]
"publicate_public/README.md" = "README.md"
[build]
outputs = ["packages.x86_64-linux.default"]
[style]
profile = "public-v1"
```

From the tool checkout, target that project with `--project /path/to/project`:

```sh
publicate_run=$(mktemp -d "${TMPDIR:-/tmp}/publicate.XXXXXX") &&
nix run . -- --project /path/to/project plan &&
nix run . -- --project /path/to/project export "$publicate_run/source" &&
nix run . -- --project /path/to/project verify "$publicate_run/source" --record "$publicate_run/verification.json"
```

Export destinations must be absent or empty; records must be outside the export.
`--policy` selects another TOML or JSON policy. `verify --fresh` discards its store.
`check CANDIDATE` runs path, input and text checks directly.
Optional `export.exclude` patterns remove paths; `style.forbid` regexes reject
matching text. Relative symlinks must resolve within the export. Selected,
initialized submodules are copied as source.

Tests, including inline test modules, can be published as selected source. To keep
specific test files private, use explicit `export.exclude` patterns such as
`["tests", "**/tests/**"]`. Excluding files can affect the project's build; preserve
its working layout and check the private and public configurations as appropriate.

Build verification for `release` and `sync` defaults to enabled. A project can
select source checks as its release default:

```toml
[build]
verify = false
outputs = ["packages.x86_64-linux.default"]
```

Source-only releases enforce export, path, pinned-input, text and declared patch
checks. Their private records report `buildVerification = "skipped"`. Add
`--verify-build` to `release` or `sync` for a build-verified run. The explicit
`verify CANDIDATE` command always builds and compares a rebuild. `build.outputs`
remains the declaration used by those build-verified runs.

See the [public source guidance](STYLE.md) for example and prose rules.

Supported source files have comments stripped by default. To restrict the paths:

```toml
[comments]
include = ["src/*.py", "nix/*.nix"]
```

Publicate packages [Uncomment](https://github.com/Goldziher/uncomment) with bundled
Tree-sitter grammars. Stripping runs before checks, tree comparison and builds;
private source is unchanged. Python docstrings, recognized directives, license
notices and comments marked `~keep` remain. `comments.preserve` adds literal
substrings to keep. Unsupported files are unchanged under automatic selection;
explicitly selected unsupported files fail export. Set `comments.enabled = false`
to disable stripping. Ordinary narration and task markers are removed.

### Patch comment verification

`.patch` and `.diff` files are unchanged by automatic stripping. Export and JSON
comparison reports list undeclared patches under `patchesUnchecked`. To check a
series, obtain its exact upstream source tree, including any prerequisite patches.
Compute a tree pin directly from its source files:

```sh
nix run . -- patch-source /path/to/upstream-source
```

Put the reported `sourceDigest` in the private project's policy:

```toml
[[patches.series]]
source = "/path/to/upstream-source"
source_digest = "REPLACE_WITH_REPORTED_SHA256"
patches = ["patches/first.patch", "patches/second.patch"]
```

`source` must be an absolute runtime directory. `.git` metadata is excluded from
its digest; file bytes, executable bits and internal relative symlinks are covered.
Patch names are exported paths and must select regular files. List patches in
application order; each series uses a fresh copy of its pinned source.

From the tool checkout, run:

```sh
nix run . -- --project /path/to/project check-patches
```

The command applies the series in temporary storage and compares each changed
file with its comment-stripped form. It reports removable text intersecting bytes
introduced or changed by that patch, with patch filename, source filename and
line number. It checks stripping idempotence in temporary source copies; the
original source and patch bytes stay fixed. Findings return exit status 1.
Edit the source patches and rerun the check. Declared series are also enforced
during export, `check`, build verification and snapshot preparation.

Findings identify introduced removable comment text. Existing upstream comments
and comment-like strings remain valid source.
Preservation rules apply, including license notices and explicit exceptions.
Byte alignment can flag existing comments when edits are ambiguous; findings
require review. Unsupported changed languages, binary files, changed symlinks,
pin mismatches and failed patch application stop the check. This checks removable
comment text. Semantic disclosure and program behavior require their own review.

The flake exposes `packages.<system>.publicate`, a default app, and `lib.mkApp`.
Use `lib.mkApp { pkgs, policyFile = "publicate.toml"; }` to load a filesystem
policy at runtime. Supply a plain string value for the filesystem location. Alternatively,
`lib.mkApp { pkgs, policy }` embeds nonsecret policy data in the Nix store.
Embedded policies can be locally readable and included in tooling caches.
For sensitive runtime policies, keep the file outside the flake source as well;
Nix evaluation can copy the flake's source files into its store.

## Private tooling dependency

A private project can declare Publicate as a Nix input and expose its exporter
through `lib.mkApp`. The published project can omit that tooling entirely.
Maintain a public flake and lockfile containing the published project's
dependencies, then remap both:

```toml
[export.files]
"publicate_public/flake.nix" = "flake.nix"
"publicate_public/flake.lock" = "flake.lock"
```

The public build and generated files must use their declared public inputs.
Review tooling dependencies and source references in the maintained public flake
and source files. Verify the exported input graph and inspect the output closure with
`nix path-info --recursive OUTPUT`; use `--store` for a separate verifier store.

The active policy filename and its file aliases are excluded from export,
including through remapping. Keep sensitive rules in a runtime policy file.
Selected submodules must have real roots inside the source tree. Lockfile URLs
permit HTTPS with supported flake parameters; arbitrary query keys are rejected.

See [local branch preparation](GIT.md) to commit a verified snapshot.
