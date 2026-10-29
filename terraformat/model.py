"""The plan model every parser produces and every renderer reads."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = 1


class Verb(StrEnum):
    """A resource change as one verb, most dangerous first."""

    DELETE = "delete"
    REPLACE = "replace"
    FORGET_REPLACE = "forget_replace"
    FORGET = "forget"
    UPDATE = "update"
    CREATE = "create"
    NO_OP = "no-op"
    READ = "read"


class Op(StrEnum):
    """A summary count, in display order."""

    IMPORT = "import"
    ADD = "add"
    CHANGE = "change"
    REPLACE = "replace"
    DESTROY = "destroy"
    MOVE = "move"
    FORGET = "forget"
    READ = "read"


class Source(StrEnum):
    """Which Terraform output a plan was read from."""

    PLAN_JSON = "plan_json"
    JSON_STREAM = "json_stream"
    TEXT = "text"


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


# Always shown; the rest only when non-zero.
CORE_OPS = (Op.ADD, Op.CHANGE, Op.DESTROY)

# Terraform's CLI symbols.
SYMBOL = {
    Verb.DELETE: "-",
    Verb.REPLACE: "-/+",
    Verb.FORGET_REPLACE: "./+",
    Verb.FORGET: ".",
    Verb.UPDATE: "~",
    Verb.CREATE: "+",
    Verb.NO_OP: " ",
    Verb.READ: "<=",
}

# As `terraform plan` counts: a replacement also adds, and destroys unless the
# old object is forgotten. Import and move ride on any verb.
VERB_OPS = {
    Verb.DELETE: (Op.DESTROY,),
    Verb.REPLACE: (Op.ADD, Op.REPLACE, Op.DESTROY),
    Verb.FORGET_REPLACE: (Op.ADD, Op.REPLACE, Op.FORGET),
    Verb.FORGET: (Op.FORGET,),
    Verb.UPDATE: (Op.CHANGE,),
    Verb.CREATE: (Op.ADD,),
    Verb.NO_OP: (),
    Verb.READ: (Op.READ,),
}

VERB_ORDER = {verb: rank for rank, verb in enumerate(Verb)}

DRIFT_SAMPLE = 20


@dataclass(frozen=True)
class Change:
    """One resource instance Terraform plans to act on."""

    address: str
    verb: Verb
    resource_type: str = ""
    moved_from: str | None = None
    importing: bool = False

    @property
    def symbol(self) -> str:
        return SYMBOL[self.verb]

    @property
    def ops(self) -> tuple[Op, ...]:
        extra = (Op.IMPORT,) * self.importing + (Op.MOVE,) * bool(self.moved_from)
        return VERB_OPS[self.verb] + extra

    def sort_key(self) -> tuple[int, str]:
        return VERB_ORDER[self.verb], self.address

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "verb": str(self.verb),
            "symbol": self.symbol,
            "resource_type": self.resource_type,
            "moved_from": self.moved_from,
            "importing": self.importing,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Change:
        return cls(
            address=data["address"],
            verb=Verb(data["verb"]),
            resource_type=data.get("resource_type", ""),
            moved_from=data.get("moved_from"),
            importing=bool(data.get("importing")),
        )


@dataclass(frozen=True)
class Diagnostic:
    """An error or warning Terraform reported, deduplicated with a count."""

    severity: Severity
    summary: str
    detail: str = ""
    filename: str = ""
    line: int | None = None
    code: str = ""
    values: tuple[str, ...] = ()
    count: int = 1

    @property
    def location(self) -> str:
        if self.filename and self.line:
            return f"{self.filename}:{self.line}"
        return self.filename

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": str(self.severity),
            "summary": self.summary,
            "detail": self.detail,
            "filename": self.filename,
            "line": self.line,
            "code": self.code,
            "values": list(self.values),
            "count": self.count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Diagnostic:
        return cls(
            severity=Severity(data["severity"]),
            summary=data["summary"],
            detail=data.get("detail", ""),
            filename=data.get("filename", ""),
            line=data.get("line"),
            code=data.get("code", ""),
            values=tuple(data.get("values", ())),
            count=data.get("count", 1),
        )


@dataclass
class Plan:
    """Everything a Terraform plan output says, whichever form it came in.

    `complete` is False when the output stops before planning finished, so
    the changes may be a prefix of the real plan.
    """

    source: Source
    changes: list[Change] = field(default_factory=list)
    drift: list[Change] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    complete: bool = True

    def __post_init__(self) -> None:
        self.changes.sort(key=Change.sort_key)
        self.drift.sort(key=Change.sort_key)

    @property
    def counts(self) -> dict[Op, int]:
        tally = Counter(op for change in self.changes for op in change.ops)
        return {op: tally[op] for op in Op}

    @property
    def has_changes(self) -> bool:
        return bool(self.changes)

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == Severity.ERROR]

    def counts_by_type(self) -> dict[str, dict[Op, int]]:
        by_type: dict[str, Counter[Op]] = {}
        for change in self.changes:
            by_type.setdefault(change.resource_type, Counter()).update(change.ops)
        return {rtype: {op: tally[op] for op in Op} for rtype, tally in sorted(by_type.items())}

    def drift_summary(self, sample: int = DRIFT_SAMPLE) -> dict[str, Any]:
        """Drift is counted and bucketed, never listed: a refresh can surface thousands."""
        by_type = Counter(d.resource_type for d in self.drift)
        return {
            "total": len(self.drift),
            "by_type": dict(by_type.most_common()),
            "sample": sorted(d.address for d in self.drift)[:sample],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "source": str(self.source),
            "complete": self.complete,
            "has_changes": self.has_changes,
            "counts": {str(op): n for op, n in self.counts.items()},
            "changes": [c.to_dict() for c in self.changes],
            "drift": [c.to_dict() for c in self.drift],
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Plan:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"terraformat schema_version {version!r}; this version reads {SCHEMA_VERSION}"
            )
        return cls(
            source=Source(data["source"]),
            changes=[Change.from_dict(c) for c in data.get("changes", [])],
            drift=[Change.from_dict(c) for c in data.get("drift", [])],
            diagnostics=[Diagnostic.from_dict(d) for d in data.get("diagnostics", [])],
            complete=data.get("complete", True),
        )
