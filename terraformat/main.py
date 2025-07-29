# terraformat/main.py
import subprocess
import sys
import click
import re
from collections import defaultdict
from .address import TerraformResourceAddress
from tabulate import tabulate  # <-- Import tabulate
from termcolor import colored

ACTIONS = {
    'create': {
        'color': 'green',
        'symbol': '+',
        'will': 'will be created',
        'to': 'to add'
    },
    'update': {
        'color': 'yellow',
        'symbol': '~',
        'will': 'will be updated in-place',
        'to': 'to change'
    },
    'replace': {
        'color': 'amber',
        'symbol': '↻',
        'will': 'will be replaced',
        'to': 'to replace',
        'include_in_summary': False  # This action is not included in the summary table as it's actually a combination of create and destroy.
    },
    'destroy': {
        'color': 'red',
        'symbol': '-',
        'will': 'will be destroyed',
        'to': 'to destroy'
    }
}


@click.command(
    context_settings=dict(
        ignore_unknown_options=True,
    )
)
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
def cli(args):
    """
    A wrapper for the Terraform CLI that provides a formatted plan summary.
    """
    # This function remains unchanged...
    command = args[0] if args else None

    if command in ['plan', 'apply', 'destroy']:
        run_terraform_plan(args)
    else:
        try:
            subprocess.run(['terraform'] + list(args), check=True)
        except subprocess.CalledProcessError as e:
            sys.exit(e.returncode)
        except FileNotFoundError:
            click.echo("Error: 'terraform' executable not found. Is Terraform installed and in your PATH?")
            sys.exit(1)


def run_terraform_plan(args):
    """
    Executes 'terraform plan', captures the output, and displays a summary.
    """
    # This function remains unchanged...
    click.echo(f"🚀 Running 'terraform {' '.join(args)}'...")
    try:
        # We use '-no-color' to get clean text output that's easy to parse.
        process = subprocess.run(
            ['terraform'] + list(args) + ['-no-color'],
            capture_output=True,
            text=True,
            check=False  # We check the return code manually
        )

        # Print the original output so the user can see details if needed
        click.echo("--- Original Terraform Output ---")
        click.echo(process.stdout)
        if process.returncode != 0 and process.returncode != 2:
            click.echo("--- Error ---", err=True)
            click.echo(process.stderr, err=True)
            sys.exit(process.returncode)

        click.echo("\n" + "=" * 50)
        click.echo("📊 Terraformat Summary")
        click.echo("=" * 50)

        summary, totals = parse_output(process.stdout)
        display_summary(summary, totals)

        # Exit with the original terraform exit code
        sys.exit(process.returncode)

    except FileNotFoundError:
        click.echo("Error: 'terraform' executable not found. Is Terraform installed and in your PATH?")
        sys.exit(1)


def parse_output(plan_output):
    """
    Parses the text output of a terraform plan using TerraformResourceAddress.
    """
    pattern = re.compile(r"# (.+) (will be created|will be updated in-place|will be destroyed|must be replaced)")

    summary = defaultdict(lambda: {a: 0 for a in ACTIONS.keys()})

    for line in plan_output.splitlines():
        if not line.strip().startswith("#"):
            continue
        match = pattern.search(line)
        if match:
            address_string, action = match.groups()
            try:
                resource = TerraformResourceAddress(address_string)
            except ValueError as e:
                click.echo(f"Warning: Could not parse address '{address_string}'. Error: {e}", err=True)
                continue

            resource_type = resource.type

            if action == 'will be created':
                summary[resource_type]['create'] += 1
            elif action == 'will be updated in-place':
                summary[resource_type]['update'] += 1
            elif action == 'will be destroyed':
                summary[resource_type]['destroy'] += 1
            elif action == 'must be replaced':
                summary[resource_type]['create'] += 1
                summary[resource_type]['destroy'] += 1

    totals = {"create": 0, "update": 0, "destroy": 0}
    summary_line_match = re.search(r"Plan: (\d+) to add, (\d+) to change, (\d+) to destroy", plan_output)
    if summary_line_match:
        totals['create'] = int(summary_line_match.group(1))
        totals['update'] = int(summary_line_match.group(2))
        totals['destroy'] = int(summary_line_match.group(3))

    return summary, totals


def color_if_nonzero(value, color):
    """
    Returns the value colored if it's greater than zero, otherwise returns the value as is.
    """
    return colored(value, color) if value > 0 else value


def display_summary(summary, totals):
    """
    Displays the parsed plan information in a grid table using the 'tabulate' library.
    """
    if not summary and all(v == 0 for v in totals.values()):
        click.echo("No changes. Your infrastructure matches the configuration.")
        return

    headers = ["Resource Type", *[action.title() for action in ACTIONS.keys()]]
    table_data = []

    # Prepare table rows
    for resource_type, counts in sorted(summary.items()):
        table_data.append([
            resource_type,
            *[
                color_if_nonzero(counts[action], action_meta["color"]) for action, action_meta in ACTIONS.items()
                if action_meta.get("include_in_summary", True)
            ],
        ])

    # Add the totals row
    table_data.append([
        "Total",
        *[
            color_if_nonzero(totals[action], action_meta["color"]) for action, action_meta in ACTIONS.items()
            if action_meta.get("include_in_summary", True)
        ],
    ])

    # Generate and print the table
    output = tabulate(
        table_data,
        headers=headers,
        tablefmt="grid",
        numalign="center"
    )
    click.echo(output)
