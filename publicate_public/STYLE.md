# Public source guidance for agents

These are review guidelines. Preserve working code, tests and accurate explanations
when a stylistic preference conflicts with them. Each project chooses its export
policy; publication does not require a particular source layout.

Write public files for someone who needs the software's behavior and interfaces.
Keep development conversations, personal motivations, operator incidents and
discarded experiments outside the export allowlist.

- Use comments and docstrings for contracts, constraints and useful implementation
  explanations. Use neutral names and diagnostics.
- Supply deployment paths, identities and endpoints through arguments or runtime
  configuration.
- Review help, errors, logs and generated text for their public audience and
  provenance. State behavior and useful next actions directly. Keep development
  session records in private documents. Useful design explanations can be public.
- Construct examples from fresh synthetic fixtures and reserved example domains.
  Select fixture generators deliberately when publishing examples or tests.
- Author publishable prose in `publicate_public/` and explicitly remap its README.
  Use deliberate selection to establish publication intent. Review examples,
  identifiers, error strings and generated resources as well as comments.
- Include useful explanations, usage, interfaces, tests and required attribution.
  Edit private source and policy, then use Publicate's `diff` and verified `sync`
  or `release` commands to update generated public trees.
- Choose formatter and lint configuration for publication explicitly.
- Prefer code organized by responsibility where that helps maintainability.
- State behavior, prerequisites and rejection conditions clearly. Use negation
  and comparisons when they convey a real limitation or useful distinction.
  Format useful exact option names, error literals and code as code.

## Tests and build layouts

Tests are ordinary source, including inline Rust `#[cfg(test)]` modules and
upstream dependency tests. Select them through the project's include/exclude
policy. Ordinary test declarations are acceptable public code. Keep existing
working layouts; Publicate requires neither test extraction nor build-time source
concatenation. If particular tests contain private material, exclude those paths
explicitly and preserve viable private and public builds with the project's
supported mechanisms.

When a change affects private-only build steps, check that configuration separately.
Export build verification covers the exported tree. Byte comparisons verify bytes;
they do not establish build success. Follow the user's build and testing constraints
and report the checks actually run.

## Mechanical checks

Set `[style] profile = "public-v1"` to reject literal home-directory paths,
selected conversation phrases and emotional openings in text lines. These rules
scan UTF-8 files, including source and Markdown. Extend `style.forbid` with private
regexes for project-specific identifiers and workflow terms. Text rules cover code
examples as well as prose. Failures report a rule ID and relative filename/line.

Enable optional Markdown wording hints explicitly:

```toml
[style]
profile = "public-v1"
prose = true
forbid = ['(?i)\bprivate-workflow\b']
```

With `prose = true`, the `negative-framing` rule flags negation and contrast
markers in Markdown prose, including wrapped wording and contractions. Fenced
blocks and inline code retain their literal wording. The default for `prose`
is false, allowing each project to adopt this check deliberately.

From a tool checkout with Python 3.11 or later and Git installed, run:

```sh
python3 src/publicate.py lint
```

`lint` checks every selected Markdown source, including remapped destinations,
and reports all finding locations. `--json` exposes structured results. Findings
return exit status 1 for review. Export and candidate checks enforce configured
`profile` and `forbid` rules; prose wording hints do not block those commands.
Avoid making optional wording lint a release gate. Private guide files belong
outside the export selection.

`check CANDIDATE` runs path, pinned-input and text checks directly. Unknown profiles,
invalid regexes and invalid style option types are errors. The scanner reads
UTF-8 files; inspect binary source and generated outputs separately.

Wording checks have false positives and false negatives. Preserve accurate meaning
instead of rewriting code or prose to satisfy a wording pattern. Human review evaluates
meaning, implied references, guideline adherence and potentially sensitive context.
Publication approval requires review of the actual selected tree and outputs.

## Dependency references

Provide a private `./publicate/publish.sh` based on Publicate's public publishing template
as the default human release entry point. Keep project-specific publishing scripts
and settings in the private repository; Publicate excludes `publish.sh` by name.
Publish reusable templates with a distinct filename such as `publish.sh.in`.
Use `publicate/review.sh` for the private ticket backchannel. Keep ticket contents
private and advertise their credential-free Git endpoint through `PUBLICATE.json`.
See [ticket conventions](TICKETS.md) for record and review contracts.
Offer minor increments through the human prompt, advance patch numbers on
conflicts, and preserve the major number through every automated path. Major
version selection requires manual review. Keep five patch snapshots per
major/minor line by default through Publicate's pruning workflow.

Pin Publicate and published components to resolved commits and content hashes.
Publish releases as exact SemVer branches, each containing one independent
snapshot. Changed published content requires a new version. Keep `main` selecting
a retained release, and retire old branches only through an explicit pruning
operation or a user-selected retention window. Retained release commit IDs stay
fixed. Consumers must retain versions they need after publisher retirement.
See [release usage](GIT.md) for the default lifecycle and legacy compatibility.
