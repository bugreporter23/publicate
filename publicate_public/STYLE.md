# Public source guidance for agents

Write public files for someone who needs the software's behavior and interfaces.
Keep development conversations, personal motivations, operator incidents and
discarded experiments outside the export allowlist.

- Limit comments and docstrings to contracts, constraints and useful implementation
  explanations. Use neutral names and diagnostics.
- Supply deployment paths, identities and endpoints through arguments or runtime
  configuration.
- Review help, errors, logs and generated text for their public audience and
  provenance. State behavior and useful next actions directly. Keep development
  rationale in private documents.
- Construct examples from fresh synthetic fixtures and reserved example domains.
  Keep fixture generators outside the public selection unless they are maintained
  public examples.
- Author publishable prose in `publicate_public/` and explicitly remap its README.
  Use deliberate selection to establish publication intent. Review examples,
  identifiers, error strings and generated resources as well as comments.
- Keep public documentation limited to usage, interfaces and required attribution.
  Edit private source and policy, then use Publicate's `diff` and verified `sync`
  or `release` commands to update generated public trees.
- Choose formatter and lint configuration for publication explicitly.
- Split operational code by responsibility. Keep source selection, content checks,
  command dispatch and build execution separately readable. Keep module imports
  limited to declarations.
- State behavior, prerequisites and rejection conditions as positive contracts.
  Format useful exact option names, error literals and code as code.

## Mechanical checks

Set `[style] profile = "public-v1"` to reject literal home-directory paths,
selected conversation phrases and emotional openings in text lines. These rules
scan UTF-8 files, including source and Markdown. Extend `style.forbid` with private
regexes for project-specific identifiers and workflow terms. Text rules cover code
examples as well as prose. Failures report a rule ID and relative filename/line.

Enable Markdown prose checking explicitly:

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
return exit status 1. Export and candidate checks enforce the same style rules
before build verification. Private guide files belong outside the export selection.

`check CANDIDATE` runs path, pinned-input and text checks directly. Unknown profiles,
invalid regexes and invalid style option types are errors. The scanner reads
UTF-8 files; inspect binary source and generated outputs separately.

Wording checks have false positives and false negatives. Human review evaluates
meaning, implied references, guideline adherence and potentially sensitive context.
Publication approval requires review of the actual selected tree and outputs.

## Dependency references

Provide a private `./publish.sh` based on Publicate's public publishing template
as the default human release entry point. Keep project-specific publishing scripts
and settings in the private repository; Publicate excludes `publish.sh` by name.
Publish reusable templates with a distinct filename such as `publish.sh.in`.

Pin Publicate and published components to resolved commits and content hashes.
Publish releases as exact SemVer branches, each containing one independent
snapshot. Changed published content requires a new version. Keep `main` selecting
a retained release, and retire old branches only through an explicit pruning
operation or a user-selected retention window. Retained release commit IDs stay
fixed. Consumers must retain versions they need after publisher retirement.
See [release usage](GIT.md) for the default lifecycle and legacy compatibility.
