"""Lint the selected Markdown sources before export."""

from pathlib import Path

from checks import style_findings
from source import selection


def lint_documents(root, policy, policy_path):
    selected, _ = selection(root, policy, policy_path)
    documents, findings = [], []
    for name, path in sorted(selected.items()):
        if (
            Path(name).suffix.lower() not in {".md", ".markdown"}
            or path.is_symlink()
        ):
            continue
        documents.append(name)
        for line, rule in style_findings(
            path.read_text(encoding="utf-8"),
            Path(name),
            policy.get("style", {}),
        ):
            findings.append(
                {
                    "path": name,
                    "source": path.relative_to(root).as_posix(),
                    "line": line,
                    "rule": rule,
                }
            )
    return {
        "status": "failed" if findings else "passed",
        "documents": documents,
        "findings": findings,
        "contentReview": "not assessed",
    }
