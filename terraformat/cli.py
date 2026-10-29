"""The `terraformat` command: render plan output, or wrap terraform and render as it goes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import click

from . import __version__
from .parse import from_plan_json, load
from .render import Format, render

# Flags after `plan` that mean the caller wants terraform's own output untouched.
PLAN_PASSTHROUGH = {"-json", "-help", "-h", "--help"}


@dataclass
class Settings:
    fmt: Format
    colour: bool | None
    output: Path | None
    terraform: str

    def emit(self, text: str) -> None:
        if self.output:
            self.output.write_text(text + "\n", encoding="utf-8")
            return
        colour = self.colour
        if colour is None:
            colour = sys.stdout.isatty() and "NO_COLOR" not in os.environ
        click.echo(text, color=colour)

    @property
    def styled(self) -> bool:
        return self.colour is not False and not self.output


def run(command: list[str]) -> int:
    """Run terraform attached to this terminal and return its exit code.

    A Ctrl-C reaches terraform too, which stops gracefully and releases its
    state lock, so wait for it rather than killing it.
    """
    try:
        process = subprocess.Popen(command)
    except FileNotFoundError:
        raise click.ClickException(
            f"{command[0]!r} not found. Is Terraform installed and on your PATH?"
        ) from None
    while True:
        try:
            return process.wait()
        except KeyboardInterrupt:
            continue


def split_globals(args: list[str]) -> tuple[list[str], str | None, list[str]]:
    """(terraform global flags such as -chdir, the subcommand, its arguments)."""
    for i, arg in enumerate(args):
        if not arg.startswith("-"):
            return args[:i], arg, args[i + 1 :]
    return args, None, []


def plan_out(args: list[str]) -> str | None:
    for i, arg in enumerate(args):
        if arg.startswith(("-out=", "--out=")):
            return arg.split("=", 1)[1]
        if arg in ("-out", "--out") and i + 1 < len(args):
            return args[i + 1]
    return None


def wrap_plan(settings: Settings, global_args: list[str], args: list[str]) -> int:
    """`terraform plan` as usual, then a summary read from the saved plan's JSON."""
    if PLAN_PASSTHROUGH.intersection(args):
        return run([settings.terraform, *global_args, "plan", *args])

    out = plan_out(args)
    scratch = None
    if out is None:
        handle, scratch = tempfile.mkstemp(prefix="terraformat-", suffix=".tfplan")
        os.close(handle)
        out = scratch
        args = [*args, f"-out={scratch}"]

    try:
        code = run([settings.terraform, *global_args, "plan", *args])
        # 2 is -detailed-exitcode's "succeeded with changes".
        if code not in (0, 2):
            return code
        shown = subprocess.run(
            [settings.terraform, *global_args, "show", "-json", out],
            capture_output=True,
            text=True,
            check=False,
        )
        if shown.returncode != 0:
            click.echo(f"terraformat: could not read the saved plan:\n{shown.stderr}", err=True)
            return code
        plan = from_plan_json(json.loads(shown.stdout))
        if not settings.output:
            click.echo()
        settings.emit(render(plan, settings.fmt, colour=settings.styled))
        if scratch:
            click.echo(
                "terraformat: that plan file was temporary and is now gone. "
                "Pass -out to keep one for apply.",
                err=True,
            )
        return code
    finally:
        if scratch:
            Path(scratch).unlink(missing_ok=True)


class TerraformGroup(click.Group):
    """terraformat's own commands, with anything else handed to terraform."""

    def resolve_command(self, ctx: click.Context, args: list[str]):
        global_args, name, rest = split_globals(args)
        if name in self.commands and not global_args:
            return super().resolve_command(ctx, args)
        ctx.meta["terraform"] = (global_args, name, rest)
        return name or "terraform", terraform_command, args


@click.command(
    "terraform",
    context_settings={"ignore_unknown_options": True, "help_option_names": []},
    add_help_option=False,
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def terraform_command(ctx: click.Context, args: tuple[str, ...]) -> None:
    settings: Settings = ctx.obj
    global_args, name, rest = ctx.meta["terraform"]
    if name == "plan":
        ctx.exit(wrap_plan(settings, global_args, rest))
    ctx.exit(run([settings.terraform, *args]))


@click.group(
    cls=TerraformGroup,
    context_settings={
        "ignore_unknown_options": True,
        "allow_interspersed_args": False,
        "help_option_names": ["--help"],
    },
    epilog="Any other command, `plan` included, runs terraform. "
    "`plan` then prints a summary of what it planned.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice([f.value for f in Format]),
    default=Format.TABLE.value,
    envvar="TERRAFORMAT_FORMAT",
    show_default=True,
    help="How to render the summary.",
)
@click.option(
    "--colour/--no-colour",
    "--color/--no-color",
    default=None,
    help="Colour the table. Defaults to on for a terminal, off when NO_COLOR is set.",
)
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write the summary to this file instead of standard output.",
)
@click.option(
    "--terraform",
    default="terraform",
    envvar="TERRAFORMAT_TERRAFORM",
    show_default=True,
    help="The terraform binary to run.",
)
@click.version_option(__version__, "--version", prog_name="terraformat")
@click.pass_context
def cli(
    ctx: click.Context, fmt: str, colour: bool | None, output: Path | None, terraform: str
) -> None:
    """Read Terraform plan output and render it as a table, markdown or JSON."""
    ctx.obj = Settings(Format(fmt), colour, output, terraform)


@cli.command("render")
@click.argument("source", type=click.File("r", encoding="utf-8"), default="-")
@click.option(
    "--detailed-exitcode",
    is_flag=True,
    help="Exit 0 for no changes, 2 for changes, 1 for errors or a plan that did not finish.",
)
@click.pass_obj
def render_command(settings: Settings, source, detailed_exitcode: bool) -> None:
    """Render SOURCE (default stdin): plan JSON, a -json stream, an HCP log or plan text."""
    if source.isatty():
        raise click.UsageError("pass a file, or pipe Terraform output in")
    try:
        plan = load(source.read())
    except ValueError as exc:
        raise click.ClickException(str(exc)) from None
    settings.emit(render(plan, settings.fmt, colour=settings.styled))
    if detailed_exitcode:
        if plan.errors or not plan.complete:
            sys.exit(1)
        sys.exit(2 if plan.has_changes else 0)


def main() -> None:
    cli(prog_name="terraformat")
