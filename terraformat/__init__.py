"""Read Terraform plan output and render it as a table, markdown or JSON."""

from importlib.metadata import PackageNotFoundError, version

from .model import SCHEMA_VERSION, Change, Diagnostic, Op, Plan, Severity, Source, Verb
from .parse import from_json_stream, from_plan_json, from_text, load
from .render import (
    Format,
    change_block,
    change_line,
    render,
    shown_ops,
    tally_phrase,
    to_json,
    to_markdown,
    to_table,
)

try:
    __version__ = version("terraformat")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "SCHEMA_VERSION",
    "Change",
    "Diagnostic",
    "Format",
    "Op",
    "Plan",
    "Severity",
    "Source",
    "Verb",
    "__version__",
    "change_block",
    "change_line",
    "from_json_stream",
    "from_plan_json",
    "from_text",
    "load",
    "render",
    "shown_ops",
    "tally_phrase",
    "to_json",
    "to_markdown",
    "to_table",
]
