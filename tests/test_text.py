from terraformat import Severity, Source, Verb, from_text
from terraformat.parse import resource_type

PLAN = """
Terraform will perform the following actions:

  # aws_instance.web will be destroyed
  - resource "aws_instance" "web" {}

  # aws_s3_bucket.logs is tainted, so must be replaced
-/+ resource "aws_s3_bucket" "logs" {}

  # aws_iam_role.ci will no longer be managed by Terraform, but will not be destroyed
 . resource "aws_iam_role" "ci" {}

  # module.vpc["a.b"].aws_subnet.private[0] will be updated in-place
  # (moved from aws_subnet.private[0])
  ~ resource "aws_subnet" "private" {}

  # aws_s3_bucket.old has moved to aws_s3_bucket.new
    resource "aws_s3_bucket" "new" {}

  # aws_s3_bucket.adopted will be imported
    resource "aws_s3_bucket" "adopted" {}

  # aws_instance.web (deposed object 1a2b3c) will be destroyed
  - resource "aws_instance" "web" {}

Plan: 1 to import, 1 to add, 1 to change, 3 to destroy.
"""


def test_headers_become_changes():
    plan = from_text(PLAN)

    verbs = {(c.address, c.verb) for c in plan.changes}
    assert ("aws_s3_bucket.logs", Verb.REPLACE) in verbs
    assert ("aws_iam_role.ci", Verb.FORGET) in verbs
    assert plan.source == Source.TEXT
    assert plan.complete

    subnet = next(c for c in plan.changes if c.address.startswith("module.vpc"))
    assert subnet.moved_from == "aws_subnet.private[0]"
    assert subnet.resource_type == "aws_subnet"

    moved = next(c for c in plan.changes if c.address == "aws_s3_bucket.new")
    assert moved.moved_from == "aws_s3_bucket.old"
    assert next(c for c in plan.changes if c.address == "aws_s3_bucket.adopted").importing

    counts = {str(op): n for op, n in plan.counts.items() if n}
    assert counts == {
        "import": 1,
        "add": 1,
        "change": 1,
        "replace": 1,
        "destroy": 3,
        "move": 2,
        "forget": 1,
    }


def test_ansi_colour_is_ignored():
    plan = from_text("\x1b[1m  # aws_s3_bucket.a\x1b[0m will be created\nPlan: 1 to add")

    assert [c.address for c in plan.changes] == ["aws_s3_bucket.a"]


def test_output_that_stops_early_is_incomplete():
    assert not from_text("  # aws_s3_bucket.a will be created\n").complete
    assert from_text("No changes. Your infrastructure matches the configuration.").complete


def test_boxed_error_is_a_diagnostic():
    text = """
╷
│ Error: Invalid reference
│
│   on main.tf line 3, in resource "aws_s3_bucket" "a":
│    3:   bucket = var.nme
│     ├────────────────
│     │ var.nme is undeclared
│
│ An input variable with the name "nme" has not been declared.
╵
"""
    (error,) = from_text(text).diagnostics

    assert error.severity == Severity.ERROR
    assert error.summary == "Invalid reference"
    assert error.location == "main.tf:3"
    assert error.code == "bucket = var.nme"
    assert error.values == ("var.nme is undeclared",)
    assert error.detail == 'An input variable with the name "nme" has not been declared.'


def test_uncoloured_warning_runs_to_the_next_section():
    text = """Warning: Some objects will no longer be managed by Terraform

If you apply this plan, Terraform will discard its tracking information.
─────────────────────────────────────────────────────────────────────────────
Saved the plan to: plan.tfplan
"""
    (warning,) = from_text(text).diagnostics

    assert warning.severity == Severity.WARNING
    assert (
        warning.detail == "If you apply this plan, Terraform will discard its tracking information."
    )


def test_resource_type_reads_past_modules_keys_and_data():
    assert resource_type('module.a["x.y"].module.b[0].aws_s3_bucket.c["k"]') == "aws_s3_bucket"
    assert resource_type("data.aws_iam_policy_document.p") == "aws_iam_policy_document"
    assert resource_type("module.a.data.aws_caller_identity.me") == "aws_caller_identity"
    assert resource_type("nonsense") == ""
