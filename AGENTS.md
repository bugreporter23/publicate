# Using Publicate as an agent

Edit the private project's source and export policy. Public checkouts are generated
outputs; use Publicate to construct and update them.

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
- Keep public prose limited to usage, interfaces and required attribution. Leave
  development narrative and operational evidence outside the export policy.
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
