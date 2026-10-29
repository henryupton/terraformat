"""Read Terraform output into a Plan.

Three forms, most faithful first:

  plan JSON    `terraform show -json <planfile>`, or HCP's /plans/:id/json-output
  JSON stream  `terraform plan -json`, or an HCP run log (JSON lines among plain text)
  plain text   `terraform plan`'s human output, best effort

`load` picks the form itself, and also reads back terraformat's own JSON.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Iterable, Iterator
from typing import Any

from .model import Change, Diagnostic, Plan, Severity, Source, Verb

# Every action list in plan JSON. Replacements come in either order.
ACTIONS_VERB = {
    ("delete",): Verb.DELETE,
    ("create", "delete"): Verb.REPLACE,
    ("create", "forget"): Verb.FORGET_REPLACE,
    ("forget",): Verb.FORGET,
    ("update",): Verb.UPDATE,
    ("create",): Verb.CREATE,
    ("no-op",): Verb.NO_OP,
    ("read",): Verb.READ,
}

# The JSON UI's `change.action`. Its "replace" also covers forget-replace,
# which the stream cannot tell apart; "remove" is a forget. Ephemeral
# open/renew/close are not resource changes.
STREAM_VERB = {
    "create": Verb.CREATE,
    "read": Verb.READ,
    "update": Verb.UPDATE,
    "replace": Verb.REPLACE,
    "delete": Verb.DELETE,
    "remove": Verb.FORGET,
    "noop": Verb.NO_OP,
    "move": Verb.NO_OP,
    "import": Verb.NO_OP,
}

TEXT_VERB = {
    "will be created": Verb.CREATE,
    "will be updated in-place": Verb.UPDATE,
    "will be destroyed": Verb.DELETE,
    "must be replaced": Verb.REPLACE,
    "is tainted, so must be replaced": Verb.REPLACE,
    "will be replaced, as requested": Verb.REPLACE,
    "will be read during apply": Verb.READ,
    "will no longer be managed by Terraform": Verb.FORGET,
    "will be imported": Verb.NO_OP,
}

ANSI = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
TEXT_HEADER = re.compile(
    r"^\s*# (?P<address>.+?)(?: \(deposed object \w+\))? "
    r"(?:(?P<phrase>" + "|".join(re.escape(p) for p in TEXT_VERB) + r")"
    r"|has moved to (?P<target>\S.*))"
)
TEXT_NOTE = re.compile(r'^\s*# \((?:imported from "[^"]*"|moved from (?P<moved_from>.+))\)\s*$')
TEXT_DONE = re.compile(r"^(?:Plan: \d+ to |No changes\.)", re.MULTILINE)
TEXT_LOCATION = re.compile(r"^on (?P<file>.+?) line (?P<line>\d+)")
TEXT_CODE = re.compile(r"^\s*(?P<line>\d+):(?P<code>.*)$")
# Without colour a diagnostic has no box; one of these ends it.
TEXT_PLAIN_DIAGNOSTIC = re.compile(r"^(?:Error|Warning): ")
TEXT_SECTION = re.compile(
    r"^(?:─|Error: |Warning: |Plan: |No changes\.|Saved the plan|Changes to Outputs|Note: )"
)


def classify(actions: Iterable[str]) -> Verb | None:
    return ACTIONS_VERB.get(tuple(sorted(actions)))


def split_address(address: str) -> list[str]:
    """Split on dots outside index brackets: `module.a["x.y"].b.c` -> 4 parts."""
    parts, current, depth, quoted = [], [], 0, False
    for i, char in enumerate(address):
        if char == '"' and address[i - 1 : i] != "\\":
            quoted = not quoted
        elif not quoted and char == "[":
            depth += 1
        elif not quoted and char == "]":
            depth -= 1
        elif char == "." and depth == 0 and not quoted:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def resource_type(address: str) -> str:
    """The resource type in an address, past any modules and a `data.` prefix."""
    parts = split_address(address)
    while len(parts) > 2 and parts[0] == "module":
        parts = parts[2:]
    if parts and parts[0] == "data":
        parts = parts[1:]
    return parts[0] if len(parts) >= 2 else ""


# Plan JSON


def _plan_change(resource: dict[str, Any]) -> Change | None:
    change = resource.get("change") or {}
    verb = classify(change.get("actions", []))
    # Dropping a data source from config destroys nothing; Terraform hides it.
    if verb is None or (verb == Verb.DELETE and resource.get("mode") == "data"):
        return None
    address = resource["address"]
    previous = resource.get("previous_address")
    moved_from = previous if previous and previous != address else None
    importing = change.get("importing") is not None
    if verb == Verb.NO_OP and not (moved_from or importing):
        return None
    return Change(
        address=address,
        verb=verb,
        resource_type=resource.get("type") or resource_type(address),
        moved_from=moved_from,
        importing=importing,
    )


def from_plan_json(plan: dict[str, Any]) -> Plan:
    changes = [c for r in plan.get("resource_changes") or [] if (c := _plan_change(r))]
    drift = [
        c
        for r in plan.get("resource_drift") or []
        if (c := _plan_change(r)) and c.verb != Verb.NO_OP
    ]
    return Plan(
        source=Source.PLAN_JSON,
        changes=changes,
        drift=drift,
        complete=not plan.get("errored", False),
    )


# JSON stream


def iter_events(lines: str | Iterable[str]) -> Iterator[dict[str, Any]]:
    """Each JSON UI event, skipping the plain-text lines an HCP log interleaves."""
    if isinstance(lines, str):
        lines = lines.splitlines()
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and "@level" in event:
            yield event


def _stream_change(change: dict[str, Any]) -> Change | None:
    verb = STREAM_VERB.get(change.get("action", ""))
    resource = change.get("resource") or {}
    address = resource.get("addr")
    if verb is None or not address:
        return None
    previous = (change.get("previous_resource") or {}).get("addr")
    return Change(
        address=address,
        verb=verb,
        resource_type=resource.get("resource_type") or resource_type(address),
        moved_from=previous if previous and previous != address else None,
        importing=change.get("importing") is not None,
    )


def _stream_diagnostic(event: dict[str, Any]) -> Diagnostic:
    diagnostic = event.get("diagnostic") or {}
    severity = diagnostic.get("severity") or event.get("@level")
    start = (diagnostic.get("range") or {}).get("start") or {}
    snippet = diagnostic.get("snippet") or {}
    return Diagnostic(
        severity=Severity.ERROR if severity == "error" else Severity.WARNING,
        summary=diagnostic.get("summary") or event.get("@message", "Error"),
        detail=(diagnostic.get("detail") or "").strip(),
        filename=(diagnostic.get("range") or {}).get("filename") or "",
        line=start.get("line"),
        code=(snippet.get("code") or "").rstrip(),
        values=tuple(
            f"{v.get('traversal', '')} {v.get('statement', '')}".strip()
            for v in snippet.get("values") or []
        ),
    )


def dedupe(diagnostics: Iterable[Diagnostic]) -> list[Diagnostic]:
    """One entry per (severity, summary, location): Terraform repeats a fault per resource."""
    seen: dict[tuple[str, str, str], Diagnostic] = {}
    for d in diagnostics:
        key = (d.severity, d.summary, d.location)
        if key in seen:
            seen[key] = dataclasses.replace(seen[key], count=seen[key].count + d.count)
        else:
            seen[key] = d
    return list(seen.values())


def from_json_stream(lines: str | Iterable[str]) -> Plan:
    """A plan from JSON UI events. Incomplete until a change_summary arrives."""
    changes: list[Change] = []
    drift: list[Change] = []
    diagnostics: list[Diagnostic] = []
    complete = False
    for event in iter_events(lines):
        kind = event.get("type")
        if kind == "planned_change":
            if change := _stream_change(event.get("change") or {}):
                changes.append(change)
        elif kind == "resource_drift":
            change = _stream_change(event.get("change") or {})
            if change and change.verb != Verb.NO_OP:
                drift.append(change)
        elif kind == "change_summary":
            complete = True
        elif "diagnostic" in event or event.get("@level") == "error":
            diagnostics.append(_stream_diagnostic(event))
    return Plan(
        source=Source.JSON_STREAM,
        changes=changes,
        drift=drift,
        diagnostics=dedupe(diagnostics),
        complete=complete,
    )


# Plain text


def _text_diagnostic(block: list[str]) -> Diagnostic | None:
    lines = [line.removeprefix("│").removeprefix(" ") for line in block]
    lines = [line for line in lines if not line.strip().startswith("├")]
    head = next((i for i, line in enumerate(lines) if line.strip()), None)
    if head is None:
        return None
    severity, _, summary = lines[head].partition(": ")
    if severity not in ("Error", "Warning"):
        return None

    filename, line_no, code, values, rest = "", None, "", [], []
    for line in lines[head + 1 :]:
        stripped = line.strip()
        if (match := TEXT_LOCATION.match(stripped)) and not filename:
            filename, line_no = match["file"], int(match["line"])
        elif (match := TEXT_CODE.match(line)) and filename and not code:
            code = match["code"].strip()
        elif stripped.startswith("│"):
            values.append(stripped.removeprefix("│").strip())
        else:
            rest.append(line.rstrip())
    return Diagnostic(
        severity=Severity.ERROR if severity == "Error" else Severity.WARNING,
        summary=summary.strip(),
        detail="\n".join(rest).strip(),
        filename=filename,
        line=line_no,
        code=code,
        values=tuple(values),
    )


def from_text(text: str) -> Plan:
    """A plan from human output. Counts what the resource headers say, no more."""
    text = ANSI.sub("", text)
    entries: list[dict[str, Any]] = []
    diagnostics: list[Diagnostic] = []
    block: list[str] | None = None
    boxed = False

    def close() -> None:
        if block and (diagnostic := _text_diagnostic(block)):
            diagnostics.append(diagnostic)

    for line in text.splitlines():
        if boxed:
            if line.startswith("╵"):
                close()
                block, boxed = None, False
            else:
                block.append(line)
            continue
        if block is not None:
            if not TEXT_SECTION.match(line):
                block.append(line)
                continue
            close()
            block = None
        if line.startswith("╷"):
            block, boxed = [], True
            continue
        if TEXT_PLAIN_DIAGNOSTIC.match(line):
            block = [line]
            continue

        if match := TEXT_HEADER.match(line):
            if match["target"]:
                entries.append(
                    {"address": match["target"], "verb": Verb.NO_OP, "moved_from": match["address"]}
                )
            else:
                verb = TEXT_VERB[match["phrase"]]
                importing = match["phrase"] == "will be imported"
                entries.append({"address": match["address"], "verb": verb, "importing": importing})
        elif entries and (note := TEXT_NOTE.match(line)):
            if note["moved_from"]:
                entries[-1]["moved_from"] = note["moved_from"]
            else:
                entries[-1]["importing"] = True

    close()
    changes = [Change(resource_type=resource_type(e["address"]), **e) for e in entries]
    return Plan(
        source=Source.TEXT,
        changes=changes,
        diagnostics=dedupe(diagnostics),
        complete=bool(TEXT_DONE.search(text)),
    )


# Detection


def _is_plan_json(doc: dict[str, Any]) -> bool:
    return any(k in doc for k in ("planned_values", "resource_changes", "resource_drift"))


def load(text: str) -> Plan:
    """A Plan from any Terraform output form, or from terraformat's own JSON."""
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            doc = json.loads(stripped)
        except json.JSONDecodeError:
            doc = None
        if isinstance(doc, dict):
            if "schema_version" in doc and "counts" in doc:
                return Plan.from_dict(doc)
            if _is_plan_json(doc):
                return from_plan_json(doc)
            if "format_version" in doc:
                raise ValueError("this is Terraform state, not a plan")
    if next(iter_events(stripped), None) is not None:
        return from_json_stream(stripped)
    return from_text(stripped)
