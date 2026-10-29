import json

import pytest
from builders import plan_json, resource_change

from terraformat import (
    SCHEMA_VERSION,
    Format,
    Op,
    Plan,
    from_plan_json,
    load,
    render,
    shown_ops,
    tally_phrase,
    to_markdown,
    to_table,
)


@pytest.fixture
def plan():
    return from_plan_json(
        plan_json(
            resource_change("aws_s3_bucket.a", ["create"]),
            resource_change("aws_s3_bucket.b", ["delete", "create"]),
            resource_change("aws_iam_role.new", ["no-op"], previous_address="aws_iam_role.old"),
        )
    )


def test_tally_phrase_names_the_extras(plan):
    assert tally_phrase(plan.counts) == "+2 ~0 -1 · 1 to replace · 1 to move"


def test_shown_ops_keeps_the_core_and_adds_what_any_plan_has(plan):
    empty = load("No changes.")

    assert shown_ops([empty.counts]) == [Op.ADD, Op.CHANGE, Op.DESTROY]
    assert shown_ops([empty.counts, plan.counts]) == [
        Op.ADD,
        Op.CHANGE,
        Op.REPLACE,
        Op.DESTROY,
        Op.MOVE,
    ]


def test_table_has_a_row_per_type_and_a_total(plan):
    lines = to_table(plan).splitlines()

    assert lines[0] == "Plan: +2 ~0 -1 · 1 to replace · 1 to move"
    assert lines[2].split() == ["Resource", "type", "Add", "Change", "Replace", "Destroy", "Move"]
    assert lines[3].split() == ["aws_iam_role", "0", "0", "0", "0", "1"]
    assert lines[4].split() == ["aws_s3_bucket", "2", "0", "1", "1", "0"]
    assert lines[5].split() == ["Total", "2", "0", "1", "1", "1"]


def test_table_colour_is_opt_in(plan):
    assert "\x1b[" not in to_table(plan)
    assert "\x1b[" in to_table(plan, colour=True)


def test_markdown_lists_changes_in_a_diff_fence(plan):
    markdown = to_markdown(plan)

    assert "| **Total** | 2 | 0 | 1 | 1 | 1 |" in markdown
    assert "```diff\n-/+ aws_s3_bucket.b\n+ aws_s3_bucket.a\n" in markdown
    assert "  aws_iam_role.new  (moved from aws_iam_role.old)" in markdown


def test_markdown_caps_the_change_list(plan):
    assert "... and 2 more" in to_markdown(plan, limit=1)


def test_markdown_flags_an_incomplete_plan():
    plan = from_plan_json(plan_json(errored=True))

    assert to_markdown(plan).startswith("> [!WARNING]")
    assert "no changes" in to_markdown(plan)


def test_json_round_trips_through_load(plan):
    document = json.loads(render(plan, Format.JSON))

    assert document["schema_version"] == SCHEMA_VERSION
    assert document["counts"]["move"] == 1
    reloaded = load(json.dumps(document))
    assert reloaded.changes == plan.changes
    assert reloaded.counts == plan.counts


def test_an_unknown_schema_version_is_refused(plan):
    document = plan.to_dict() | {"schema_version": SCHEMA_VERSION + 1}

    with pytest.raises(ValueError, match="schema_version"):
        Plan.from_dict(document)


def test_state_json_is_not_a_plan():
    with pytest.raises(ValueError, match="state"):
        load(json.dumps({"format_version": "1.0", "values": {}}))
