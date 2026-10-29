from builders import change_summary, diagnostic, event, planned_change

from terraformat import Source, Verb, from_json_stream


def stream(*lines: str) -> str:
    return "\n".join(lines)


def counts(plan):
    return {str(op): n for op, n in plan.counts.items() if n}


def test_a_move_only_hcp_log_reports_its_moves():
    # HCP logs interleave plain text with the JSON UI lines.
    log = stream(
        "Terraform v1.14.3",
        "on linux_amd64",
        planned_change(
            'module.new["a"].google_service_account.sa["a"]',
            "move",
            previous='module.old["a"].google_service_account.sa["a"]',
        ),
        planned_change(
            'module.new["a"].google_project_iam_member.role["a=>roles/viewer"]',
            "move",
            previous='module.old["a"].google_project_iam_member.role["a=>roles/viewer"]',
        ),
        change_summary(),
    )
    plan = from_json_stream(log)

    assert plan.source == Source.JSON_STREAM
    assert plan.complete
    assert plan.has_changes
    assert counts(plan) == {"move": 2}
    assert {c.resource_type for c in plan.changes} == {
        "google_service_account",
        "google_project_iam_member",
    }


def test_stream_actions_map_to_verbs():
    plan = from_json_stream(
        stream(
            planned_change("aws_s3_bucket.create", "create"),
            planned_change("aws_s3_bucket.update", "update"),
            planned_change("aws_s3_bucket.delete", "delete"),
            planned_change("aws_s3_bucket.replace", "replace"),
            planned_change("aws_s3_bucket.forget", "remove"),
            planned_change("data.aws_iam_policy.read", "read"),
            planned_change("aws_s3_bucket.imported", "import", importing={"id": "b"}),
            change_summary(),
        )
    )

    assert counts(plan) == {
        "import": 1,
        "add": 2,
        "change": 1,
        "replace": 1,
        "destroy": 2,
        "forget": 1,
        "read": 1,
    }
    by_address = {c.address: c.verb for c in plan.changes}
    assert by_address["aws_s3_bucket.forget"] == Verb.FORGET
    assert by_address["aws_s3_bucket.imported"] == Verb.NO_OP


def test_ephemeral_actions_are_not_changes():
    plan = from_json_stream(
        stream(planned_change("ephemeral.aws_secret.token", "open"), change_summary())
    )

    assert plan.changes == []


def test_a_stream_without_a_change_summary_is_incomplete():
    plan = from_json_stream(stream(planned_change("aws_s3_bucket.a", "create")))

    assert not plan.complete
    assert plan.counts["add"] == 1


def test_diagnostics_are_deduplicated_with_a_count():
    plan = from_json_stream(
        stream(
            diagnostic("Invalid count argument", filename="main.tf", line=3),
            diagnostic("Invalid count argument", filename="main.tf", line=3),
            diagnostic("Invalid count argument", filename="other.tf", line=9),
        )
    )

    assert [(d.location, d.count) for d in plan.errors] == [("main.tf:3", 2), ("other.tf:9", 1)]
    assert not plan.complete


def test_a_bare_error_event_becomes_a_diagnostic():
    plan = from_json_stream(stream(event("log", level="error", **{"@message": "boom"})))

    assert [d.summary for d in plan.errors] == ["boom"]


def test_resource_drift_events_are_drift():
    plan = from_json_stream(
        stream(
            planned_change("aws_s3_bucket.a", "update", kind="resource_drift"),
            planned_change("aws_s3_bucket.b", "noop", kind="resource_drift"),
            change_summary(),
        )
    )

    assert [d.address for d in plan.drift] == ["aws_s3_bucket.a"]
    assert not plan.has_changes
