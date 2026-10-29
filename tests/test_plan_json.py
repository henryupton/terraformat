import pytest
from builders import plan_json, resource_change

from terraformat import Op, Source, Verb, from_plan_json


def counts(plan):
    return {str(op): n for op, n in plan.counts.items() if n}


@pytest.mark.parametrize(
    ("actions", "verb", "expected"),
    [
        (["create"], Verb.CREATE, {"add": 1}),
        (["update"], Verb.UPDATE, {"change": 1}),
        (["delete"], Verb.DELETE, {"destroy": 1}),
        (["delete", "create"], Verb.REPLACE, {"add": 1, "replace": 1, "destroy": 1}),
        (["create", "delete"], Verb.REPLACE, {"add": 1, "replace": 1, "destroy": 1}),
        (["forget"], Verb.FORGET, {"forget": 1}),
        (["create", "forget"], Verb.FORGET_REPLACE, {"add": 1, "replace": 1, "forget": 1}),
        (["read"], Verb.READ, {"read": 1}),
    ],
)
def test_each_action_counts_as_terraform_plan_does(actions, verb, expected):
    plan = from_plan_json(plan_json(resource_change("aws_s3_bucket.a", actions)))

    assert [c.verb for c in plan.changes] == [verb]
    assert counts(plan) == expected


def test_a_plain_no_op_is_not_a_change():
    plan = from_plan_json(plan_json(resource_change("aws_s3_bucket.a", ["no-op"])))

    assert plan.changes == []
    assert not plan.has_changes


def test_a_move_only_plan_has_changes():
    plan = from_plan_json(
        plan_json(
            resource_change(
                "module.new.aws_s3_bucket.a",
                ["no-op"],
                previous_address="module.old.aws_s3_bucket.a",
            )
        )
    )

    assert plan.has_changes
    assert counts(plan) == {"move": 1}
    assert plan.changes[0].moved_from == "module.old.aws_s3_bucket.a"


def test_an_import_only_plan_has_changes():
    plan = from_plan_json(
        plan_json(resource_change("aws_s3_bucket.a", ["no-op"], importing={"id": "bucket"}))
    )

    assert counts(plan) == {"import": 1}
    assert plan.changes[0].importing


def test_import_and_move_ride_on_other_verbs():
    plan = from_plan_json(
        plan_json(
            resource_change(
                "aws_s3_bucket.b",
                ["update"],
                previous_address="aws_s3_bucket.a",
                importing={"id": "bucket"},
            )
        )
    )

    assert counts(plan) == {"change": 1, "import": 1, "move": 1}


def test_dropping_a_data_source_destroys_nothing():
    plan = from_plan_json(
        plan_json(resource_change("data.aws_iam_policy.a", ["delete"], mode="data"))
    )

    assert plan.changes == []


def test_changes_sort_most_dangerous_first():
    plan = from_plan_json(
        plan_json(
            resource_change("aws_s3_bucket.create", ["create"]),
            resource_change("aws_s3_bucket.delete", ["delete"]),
            resource_change("aws_s3_bucket.update", ["update"]),
        )
    )

    assert [c.verb for c in plan.changes] == [Verb.DELETE, Verb.UPDATE, Verb.CREATE]


def test_drift_skips_no_ops_and_buckets_by_type():
    drift = [
        resource_change("aws_s3_bucket.a", ["update"]),
        resource_change("aws_s3_bucket.b", ["delete"]),
        resource_change("aws_iam_role.c", ["update"]),
        resource_change("aws_iam_role.d", ["no-op"]),
    ]
    plan = from_plan_json(plan_json(drift=drift))

    assert plan.drift_summary() == {
        "total": 3,
        "by_type": {"aws_s3_bucket": 2, "aws_iam_role": 1},
        "sample": ["aws_iam_role.c", "aws_s3_bucket.a", "aws_s3_bucket.b"],
    }
    assert not plan.has_changes


def test_an_errored_plan_is_incomplete():
    plan = from_plan_json(plan_json(errored=True))

    assert plan.source == Source.PLAN_JSON
    assert not plan.complete


def test_counts_by_type():
    plan = from_plan_json(
        plan_json(
            resource_change("aws_s3_bucket.a", ["create"]),
            resource_change("aws_s3_bucket.b", ["create"]),
            resource_change("aws_iam_role.c", ["delete"]),
        )
    )

    by_type = plan.counts_by_type()
    assert by_type["aws_s3_bucket"][Op.ADD] == 2
    assert by_type["aws_iam_role"][Op.DESTROY] == 1
