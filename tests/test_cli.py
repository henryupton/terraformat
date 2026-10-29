import json
import stat
import sys
from pathlib import Path

import pytest
from builders import plan_json, resource_change
from click.testing import CliRunner

from terraformat.cli import cli

FIXTURES = Path(__file__).parent / "fixtures" / "terraform_data"


@pytest.fixture
def fake_terraform(tmp_path):
    """A terraform that logs its argv, exits with $FAKE_TF_EXIT, and shows a fixed plan."""
    log = tmp_path / "calls.jsonl"
    plan = json.dumps(plan_json(resource_change("aws_s3_bucket.a", ["create"])))
    script = tmp_path / "terraform"
    script.write_text(
        f"""#!{sys.executable}
import json, os, sys
args = sys.argv[1:]
with open({str(log)!r}, "a") as f:
    f.write(json.dumps(args) + "\\n")
if "show" in args:
    print({plan!r})
    sys.exit(0)
sys.exit(int(os.environ.get("FAKE_TF_EXIT", "0")))
"""
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)

    def calls():
        return [json.loads(line) for line in log.read_text().splitlines()]

    return script, calls


def invoke(*args, env=None, input=None):
    return CliRunner().invoke(cli, list(args), env=env, input=input, catch_exceptions=False)


def test_render_reads_a_file_and_detects_its_form():
    result = invoke("--format", "json", "render", str(FIXTURES / "stream.jsonl"))

    assert result.exit_code == 0
    assert json.loads(result.output)["source"] == "json_stream"


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("No changes. Your infrastructure matches the configuration.", 0),
        ("  # aws_s3_bucket.a will be created\nPlan: 1 to add", 2),
        ("  # aws_s3_bucket.a will be created\n", 1),
    ],
)
def test_render_detailed_exitcode(text, code):
    assert invoke("render", "--detailed-exitcode", "-", input=text).exit_code == code


def test_plan_saves_to_a_temp_file_shows_it_then_removes_it(fake_terraform):
    script, calls = fake_terraform
    result = invoke("--terraform", str(script), "--no-colour", "plan", "-input=false")

    assert result.exit_code == 0
    plan_call, show_call = calls()
    assert plan_call[:2] == ["plan", "-input=false"]
    assert plan_call[2].startswith("-out=")
    scratch = plan_call[2].removeprefix("-out=")
    assert show_call == ["show", "-json", scratch]
    assert not Path(scratch).exists()
    assert "Plan: +1 ~0 -0" in result.output


def test_plan_keeps_global_flags_and_a_caller_out(fake_terraform, tmp_path):
    script, calls = fake_terraform
    out = str(tmp_path / "keep.tfplan")
    invoke("--terraform", str(script), "-chdir=infra", "plan", "-out", out)

    assert calls() == [
        ["-chdir=infra", "plan", "-out", out],
        ["-chdir=infra", "show", "-json", out],
    ]


def test_plan_passes_terraforms_exit_code_through(fake_terraform):
    script, calls = fake_terraform
    result = invoke("--terraform", str(script), "plan", env={"FAKE_TF_EXIT": "2"})
    assert result.exit_code == 2
    assert len(calls()) == 2

    failed = invoke("--terraform", str(script), "plan", env={"FAKE_TF_EXIT": "1"})
    assert failed.exit_code == 1
    assert len(calls()) == 3


def test_plan_json_is_left_to_terraform(fake_terraform):
    script, calls = fake_terraform
    invoke("--terraform", str(script), "plan", "-json")

    assert calls() == [["plan", "-json"]]


def test_other_commands_pass_straight_through(fake_terraform):
    script, calls = fake_terraform
    result = invoke("--terraform", str(script), "apply", "-auto-approve", env={"FAKE_TF_EXIT": "3"})

    assert result.exit_code == 3
    assert calls() == [["apply", "-auto-approve"]]


def test_output_writes_the_summary_to_a_file(fake_terraform, tmp_path):
    script, _ = fake_terraform
    summary = tmp_path / "summary.md"
    invoke("--terraform", str(script), "--format", "markdown", "--output", str(summary), "plan")

    assert summary.read_text().startswith("**Plan:** +1 ~0 -0")
