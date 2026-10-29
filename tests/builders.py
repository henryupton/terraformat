"""Minimal Terraform output shapes, so each test states only what it is about."""

from __future__ import annotations

import json
from typing import Any


def resource_change(
    address: str,
    actions: list[str],
    *,
    mode: str = "managed",
    previous_address: str | None = None,
    importing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    change: dict[str, Any] = {"actions": actions}
    if importing is not None:
        change["importing"] = importing
    entry: dict[str, Any] = {
        "address": address,
        "mode": mode,
        "type": address.split(".")[-2],
        "change": change,
    }
    if previous_address:
        entry["previous_address"] = previous_address
    return entry


def plan_json(*changes: dict[str, Any], drift: list[dict] | None = None, **extra) -> dict:
    return {
        "format_version": "1.2",
        "planned_values": {},
        "resource_changes": list(changes),
        "resource_drift": drift or [],
        **extra,
    }


def event(kind: str, **fields: Any) -> str:
    return json.dumps(
        {"@level": fields.pop("level", "info"), "@message": "", "type": kind, **fields}
    )


def planned_change(
    address: str,
    action: str,
    *,
    previous: str | None = None,
    importing: dict[str, Any] | None = None,
    kind: str = "planned_change",
) -> str:
    resource_type = address.split(".")[-2]
    change: dict[str, Any] = {
        "resource": {"addr": address, "resource_type": resource_type},
        "action": action,
    }
    if previous:
        change["previous_resource"] = {"addr": previous}
    if importing is not None:
        change["importing"] = importing
    return event(kind, change=change)


def change_summary() -> str:
    return event(
        "change_summary",
        changes={"add": 0, "change": 0, "import": 0, "remove": 0, "operation": "plan"},
    )


def diagnostic(summary: str, *, filename: str = "", line: int | None = None) -> str:
    body: dict[str, Any] = {"severity": "error", "summary": summary, "detail": "why"}
    if filename:
        body["range"] = {"filename": filename, "start": {"line": line}}
    return event("diagnostic", level="error", diagnostic=body)
