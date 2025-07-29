# tests/test_parser.py
import json

import pytest
from collections import defaultdict
from terraformat.main import parse_output

# --- Test Data: Mock Terraform Plan Outputs ---

PLAN_MIXED_ACTIONS = """
An execution plan has been generated and is shown below.
Resource actions are indicated with the following symbols:
  + create
  ~ update in-place
  - destroy

Terraform will perform the following actions:

  # aws_instance.web will be destroyed
  - resource "aws_instance" "web" {
      - ami           = "ami-0c55b159cbfafe1f0" -> null
      - id            = "i-0123456789abcdef0" -> null
    }

  # local_file.example will be created
  + resource "local_file" "example" {
      + content  = "hello world"
      + filename = "hello.txt"
      + id       = (known after apply)
    }

  # random_pet.my_pet will be updated in-place
  ~ resource "random_pet" "my_pet" {
      ~ length = 2 -> 3
        id     = "fluffy-cat"
    }

Plan: 1 to add, 1 to change, 1 to destroy.
"""

PLAN_NO_CHANGES = """
No changes. Your infrastructure matches the configuration.

Terraform has compared your real infrastructure against your configuration
and found no differences, so no changes are needed.
"""


# --- Unit Tests ---

def test_parse_plan_with_mixed_actions():
    """Tests a typical plan with create, update, and destroy actions."""
    summary, totals = parse_output(PLAN_MIXED_ACTIONS)

    print(json.dumps(summary, indent=2))

    # Check the per-resource summary
    assert summary['aws_instance']['destroy'] == 1
    assert summary['local_file']['create'] == 1
    assert summary['random_pet']['update'] == 1

    # Check that other actions for these resources are zero
    assert summary['aws_instance']['create'] == 0
    assert summary['local_file']['update'] == 0

    # Check the grand totals from the "Plan:" line
    assert totals == {'create': 1, 'update': 1, 'destroy': 1}


def test_parse_plan_with_no_changes():
    """Tests a plan where no changes are detected."""
    summary, totals = parse_output(PLAN_NO_CHANGES)

    # Both the summary and totals should be empty/zero
    assert not summary
    assert totals == {'create': 0, 'update': 0, 'destroy': 0}


def test_parse_empty_input():
    """Ensures the parser handles empty string input gracefully."""
    summary, totals = parse_output("")

    assert not summary
    assert totals == {'create': 0, 'update': 0, 'destroy': 0}
