"""Inspect Markdown prose while preserving diagnostic line numbers."""

import re


NEGATIVE_FRAMING = re.compile(
    r"\b(?:no|not|never|without|unlike|instead|neither|cannot)\b"
    r"|\brather\s+than\b|\b[a-z]+n['’]t\b",
    re.IGNORECASE,
)


def blank(text):
    return "".join(
        character if character in "\r\n" else " " for character in text
    )


def markdown_prose(text):
    lines = []
    fence = None
    for line in text.splitlines(keepends=True):
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            if re.match(
                rf"^ {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}[ \t]*\r?\n?$",
                line,
            ):
                fence = None
            lines.append(blank(line))
        elif opening:
            fence = opening[1]
            lines.append(blank(line))
        else:
            lines.append(line)
    material = "".join(lines)
    runs = list(re.finditer(r"`+", material))
    masked = list(material)
    index = 0
    while index < len(runs):
        opening = runs[index]
        preceding = material[: opening.start()]
        escapes = len(preceding) - len(preceding.rstrip("\\"))
        if escapes % 2:
            index += 1
            continue
        closing = next(
            (
                number
                for number in range(index + 1, len(runs))
                if len(runs[number][0]) == len(opening[0])
            ),
            None,
        )
        if closing is None:
            index += 1
            continue
        end = runs[closing].end()
        masked[opening.start() : end] = blank(material[opening.start() : end])
        index = closing + 1
    return "".join(masked)


def prose_findings(text):
    material = markdown_prose(text)
    return sorted(
        {
            (material.count("\n", 0, match.start()) + 1, "negative-framing")
            for match in NEGATIVE_FRAMING.finditer(material)
        }
    )
