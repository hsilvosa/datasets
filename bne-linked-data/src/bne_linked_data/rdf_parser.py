from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Triple:
    subject: str
    predicate: str
    object: str
    object_kind: str
    language: str | None
    datatype: str | None


def _unicode_escape(value: str) -> str:
    output: list[str] = []
    index = 0
    simple = {"t": "\t", "b": "\b", "n": "\n", "r": "\r", "f": "\f", '"': '"', "'": "'", "\\": "\\"}
    while index < len(value):
        if value[index] != "\\":
            output.append(value[index])
            index += 1
            continue
        if index + 1 >= len(value):
            raise ValueError("Trailing backslash")
        escape = value[index + 1]
        if escape in simple:
            output.append(simple[escape])
            index += 2
        elif escape in {"u", "U"}:
            width = 4 if escape == "u" else 8
            digits = value[index + 2 : index + 2 + width]
            if len(digits) != width:
                raise ValueError("Incomplete Unicode escape")
            output.append(chr(int(digits, 16)))
            index += width + 2
        else:
            raise ValueError(f"Unsupported escape: \\{escape}")
    return "".join(output)


def _term_end(line: str, start: int) -> int:
    if line[start] == "<":
        end = line.find(">", start + 1)
        if end < 0:
            raise ValueError("Unterminated IRI")
        return end + 1
    if line.startswith("_:", start):
        end = start + 2
        while end < len(line) and not line[end].isspace():
            end += 1
        return end
    raise ValueError("Expected IRI or blank node")


def _resource_value(token: str) -> str:
    if token.startswith("<") and token.endswith(">"):
        return _unicode_escape(token[1:-1])
    if token.startswith("_:"):
        return token
    raise ValueError("Invalid resource token")


def parse_ntriples_line(raw_line: str) -> Triple | None:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None
    if not line.endswith("."):
        raise ValueError("Triple must end with a period")
    content = line[:-1].rstrip()
    subject_end = _term_end(content, 0)
    subject_token = content[:subject_end]
    cursor = subject_end
    while cursor < len(content) and content[cursor].isspace():
        cursor += 1
    predicate_end = _term_end(content, cursor)
    predicate_token = content[cursor:predicate_end]
    if not predicate_token.startswith("<"):
        raise ValueError("Predicate must be an IRI")
    cursor = predicate_end
    while cursor < len(content) and content[cursor].isspace():
        cursor += 1
    object_token = content[cursor:]
    if not object_token:
        raise ValueError("Missing object")

    language: str | None = None
    datatype: str | None = None
    if object_token[0] == '"':
        escaped = False
        closing = None
        for index in range(1, len(object_token)):
            char = object_token[index]
            if char == '"' and not escaped:
                closing = index
                break
            if char == "\\":
                escaped = not escaped
            else:
                escaped = False
        if closing is None:
            raise ValueError("Unterminated literal")
        value = _unicode_escape(object_token[1:closing])
        suffix = object_token[closing + 1 :]
        if suffix.startswith("@"):
            language = suffix[1:]
        elif suffix.startswith("^^<") and suffix.endswith(">"):
            datatype = _unicode_escape(suffix[3:-1])
        elif suffix:
            raise ValueError("Invalid literal suffix")
        kind = "literal"
    elif object_token.startswith("<"):
        value = _resource_value(object_token)
        kind = "iri"
    elif object_token.startswith("_:"):
        value = object_token
        kind = "blank_node"
    else:
        raise ValueError("Unsupported object")
    return Triple(
        subject=_resource_value(subject_token),
        predicate=_resource_value(predicate_token),
        object=value,
        object_kind=kind,
        language=language or None,
        datatype=datatype,
    )

