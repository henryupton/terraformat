"""Real Terraform 1.14 output for `fixtures/terraform_data/main.tf`, in all three forms.

The config was applied, then edited to update, move, destroy, forget, replace
and create one `terraform_data` each. Every form must tell the same story.
"""

from pathlib import Path

import pytest

from terraformat import Source, load

FIXTURES = Path(__file__).parent / "fixtures" / "terraform_data"

EXPECTED_COUNTS = {"add": 2, "change": 1, "replace": 1, "destroy": 2, "move": 1, "forget": 1}
EXPECTED_CHANGES = [
    ("-", "terraform_data.gone", None),
    ("-/+", "terraform_data.swap", None),
    (".", "terraform_data.forget_me", None),
    ("~", "terraform_data.keep", None),
    ("+", "terraform_data.fresh", None),
    (" ", "terraform_data.new_name", "terraform_data.old_name"),
]


@pytest.mark.parametrize(
    ("name", "source"),
    [
        ("plan.json", Source.PLAN_JSON),
        ("stream.jsonl", Source.JSON_STREAM),
        ("plan.txt", Source.TEXT),
    ],
)
def test_every_form_agrees(name, source):
    plan = load((FIXTURES / name).read_text(encoding="utf-8"))

    assert plan.source == source
    assert plan.complete
    assert {str(op): n for op, n in plan.counts.items() if n} == EXPECTED_COUNTS
    assert [(c.symbol, c.address, c.moved_from) for c in plan.changes] == EXPECTED_CHANGES
    assert {c.resource_type for c in plan.changes} == {"terraform_data"}


@pytest.mark.parametrize("name", ["stream.jsonl", "plan.txt"])
def test_the_forget_warning_comes_through(name):
    plan = load((FIXTURES / name).read_text(encoding="utf-8"))

    assert [d.summary for d in plan.diagnostics] == [
        "Some objects will no longer be managed by Terraform"
    ]
    assert plan.errors == []
