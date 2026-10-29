"""Render a Plan as a terminal table, GitHub-flavoured markdown or JSON."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from enum import StrEnum

import click

from .model import CORE_OPS, Change, Diagnostic, Op, Plan

MAX_LISTED_CHANGES = 60
MAX_LISTED_DIAGNOSTICS = 8

OP_COLOUR = {
    Op.IMPORT: "cyan",
    Op.ADD: "green",
    Op.CHANGE: "yellow",
    Op.REPLACE: "magenta",
    Op.DESTROY: "red",
    Op.MOVE: "blue",
    Op.FORGET: "bright_black",
    Op.READ: "bright_black",
}

INCOMPLETE = "Planning did not finish, so these are only the changes planned before it stopped."


class Format(StrEnum):
    TABLE = "table"
    MARKDOWN = "markdown"
    JSON = "json"


def shown_ops(counts: Iterable[Mapping[Op, int]]) -> list[Op]:
    """Add, change and destroy, then any other op some plan in `counts` has."""
    counts = list(counts)
    return [op for op in Op if op in CORE_OPS or any(c.get(op, 0) for c in counts)]


def tally_phrase(counts: Mapping[Op, int]) -> str:
    """`+1 ~2 -3`, then every other non-zero count in words: `+1 ~0 -0 · 2 to move`."""
    core = f"+{counts[Op.ADD]} ~{counts[Op.CHANGE]} -{counts[Op.DESTROY]}"
    extras = [f"{counts[op]} to {op}" for op in Op if op not in CORE_OPS and counts.get(op, 0)]
    return " · ".join([core, *extras])


def change_line(change: Change) -> str:
    """Terraform's symbol, the address, and any move or import, for a `diff` fence."""
    notes = []
    if change.moved_from:
        notes.append(f"moved from {change.moved_from}")
    if change.importing:
        notes.append("importing")
    suffix = f"  ({', '.join(notes)})" if notes else ""
    return f"{change.symbol} {change.address}{suffix}"


def diagnostic_line(diagnostic: Diagnostic) -> str:
    where = f" ({diagnostic.location})" if diagnostic.location else ""
    times = f" ×{diagnostic.count}" if diagnostic.count > 1 else ""
    return f"{diagnostic.severity.title()}: {diagnostic.summary}{where}{times}"


def drift_phrase(plan: Plan) -> str:
    drift = plan.drift_summary()
    buckets = ", ".join(f"{t} ×{n}" for t, n in list(drift["by_type"].items())[:5])
    return f"{drift['total']:,} resource(s) drifted outside Terraform ({buckets})."


# Table


def _table_rows(plan: Plan, ops: list[Op]) -> list[list[str]]:
    rows = [
        [rtype or "(unknown)", *(str(counts[op]) for op in ops)]
        for rtype, counts in plan.counts_by_type().items()
    ]
    rows.append(["Total", *(str(plan.counts[op]) for op in ops)])
    return rows


def to_table(plan: Plan, colour: bool = False) -> str:
    def style(text: str, **kwargs) -> str:
        return click.style(text, **kwargs) if colour else text

    lines = []
    if not plan.complete:
        lines.extend([style(INCOMPLETE, fg="yellow"), ""])
    if plan.has_changes:
        ops = shown_ops([plan.counts])
        header = ["Resource type", *(op.title() for op in ops)]
        rows = _table_rows(plan, ops)
        widths = [max(len(r[i]) for r in [header, *rows]) for i in range(len(header))]
        lines.append(f"Plan: {tally_phrase(plan.counts)}")
        lines.append("")
        lines.append("  ".join(style(h.ljust(widths[i]), bold=True) for i, h in enumerate(header)))
        for n, row in enumerate(rows):
            cells = [row[0].ljust(widths[0])]
            for i, (op, value) in enumerate(zip(ops, row[1:], strict=True), start=1):
                cell = value.rjust(widths[i])
                cells.append(style(cell, fg=OP_COLOUR[op]) if value != "0" else cell)
            line = "  ".join(cells)
            lines.append(style(line, bold=True) if n == len(rows) - 1 else line)
    else:
        lines.append("No changes.")

    if plan.drift:
        lines.extend(["", drift_phrase(plan)])
    for diagnostic in plan.diagnostics[:MAX_LISTED_DIAGNOSTICS]:
        fg = "red" if diagnostic.severity == "error" else "yellow"
        lines.extend(["", style(diagnostic_line(diagnostic), fg=fg)])
    return "\n".join(lines)


# Markdown


def _markdown_diagnostics(diagnostics: list[Diagnostic]) -> list[str]:
    if not diagnostics:
        return []
    lines = ["", "**Diagnostics**", ""]
    for d in diagnostics[:MAX_LISTED_DIAGNOSTICS]:
        where = f" (`{d.location}`)" if d.location else ""
        times = f" ×{d.count}" if d.count > 1 else ""
        lines.append(f"- **{d.severity.title()}: {d.summary}**{where}{times}")
        if d.code:
            gutter = f"{d.line}: " if d.line else ""
            lines.extend(["", "  ```hcl", f"  {gutter}{d.code}", "  ```"])
        lines.extend(f"  <sub>{value}</sub>" for value in d.values)
        if d.detail:
            lines.extend(["", "  ```", *(f"  {ln}" for ln in d.detail.splitlines()), "  ```"])
    if len(diagnostics) > MAX_LISTED_DIAGNOSTICS:
        lines.append(f"- ... and {len(diagnostics) - MAX_LISTED_DIAGNOSTICS} more")
    return lines


def change_block(plan: Plan, limit: int = MAX_LISTED_CHANGES) -> list[str]:
    """The change list as a ```diff fence, which colours `+` green and `-` red."""
    if not plan.changes:
        return []
    listed = [change_line(c) for c in plan.changes[:limit]]
    if len(plan.changes) > limit:
        listed.append(f"... and {len(plan.changes) - limit} more")
    return ["```diff", *listed, "```"]


def to_markdown(plan: Plan, limit: int = MAX_LISTED_CHANGES) -> str:
    lines = []
    if not plan.complete:
        lines.extend([f"> [!WARNING]\n> {INCOMPLETE}", ""])
    if plan.has_changes:
        ops = shown_ops([plan.counts])
        lines.append(f"**Plan:** {tally_phrase(plan.counts)}")
        lines.extend(["", f"| Resource type | {' | '.join(op.title() for op in ops)} |"])
        lines.append(f"|---|{'---:|' * len(ops)}")
        rows = _table_rows(plan, ops)
        for n, row in enumerate(rows):
            name = f"**{row[0]}**" if n == len(rows) - 1 else f"`{row[0]}`"
            lines.append(f"| {name} | {' | '.join(row[1:])} |")
        count = len(plan.changes)
        lines.extend(["", f"<details><summary>{count} change{'s' * (count != 1)}</summary>", ""])
        lines.extend(change_block(plan, limit))
        lines.extend(["", "</details>"])
    else:
        lines.append("**Plan:** no changes.")
    if plan.drift:
        lines.extend(["", f"<sub>{drift_phrase(plan)}</sub>"])
    lines.extend(_markdown_diagnostics(plan.diagnostics))
    return "\n".join(lines)


# JSON


def to_json(plan: Plan) -> str:
    return json.dumps(plan.to_dict(), indent=2)


def render(plan: Plan, fmt: Format = Format.TABLE, colour: bool = False) -> str:
    if fmt == Format.MARKDOWN:
        return to_markdown(plan)
    if fmt == Format.JSON:
        return to_json(plan)
    return to_table(plan, colour=colour)
