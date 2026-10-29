# terraformat

terraformat reads Terraform plan output and renders it as a terminal table, GitHub-flavoured markdown or JSON. It reads all three forms Terraform produces, and it can wrap `terraform` so `plan` prints the summary as it goes.

```text
Plan: +2 ~1 -2 · 1 to replace · 1 to move · 1 to forget

Resource type   Add  Change  Replace  Destroy  Move  Forget
terraform_data    2       1        1        2     1       1
Total             2       1        1        2     1       1
```

## Install

```bash
pip install terraformat
```

or, as a standalone tool:

```bash
uv tool install terraformat
```

It needs Python 3.11 or later. The wrapper also needs `terraform` on your `PATH`, or `--terraform` pointing at it.

## Inputs

`terraformat render` and `terraformat.load()` work out which form they've been given.

| Form | How to get it | Limits |
|---|---|---|
| Plan JSON | `terraform show -json plan.tfplan`, or HCP Terraform's `/plans/:id/json-output` | None. This is the most faithful form. |
| JSON stream | `terraform plan -json`, or an HCP Terraform run log | Reports a forget-replace as a replace, so it counts as a destroy. A stream with no closing `change_summary` is marked incomplete. |
| Plain text | `terraform plan`, with or without colour | Reads the `# address will be ...` headers and the error and warning blocks. No drift. |

terraformat also reads back its own JSON output, so a summary written in one CI job can be rendered in another.

## Operations

| Column | Counts | Notes |
|---|---|---|
| Import | Resources being imported | Counted alongside whatever else happens to the resource. |
| Add | Creates, replacements included | Matches `terraform plan`'s "to add". |
| Change | In-place updates | |
| Replace | Replacements | Also counted in Add, and in Destroy unless the old object is forgotten. |
| Destroy | Deletes, replacements included | Dropping a data source from config is not a destroy. |
| Move | Address changes from a `moved` block | A resource that only moves still counts as a change. |
| Forget | Resources leaving state without being destroyed, from a `removed` block | |
| Read | Data sources read during apply | |

Add, Change and Destroy always show. The others show only when they're non-zero.

## Wrap terraform

```bash
terraformat plan
terraformat --format markdown --output plan.md -chdir=infra plan -detailed-exitcode
```

`terraformat plan` runs `terraform plan` with its usual output, saves the plan, then prints the summary from `terraform show -json`. Without your own `-out`, the saved plan goes to a temporary file that is removed afterwards. terraformat exits with terraform's exit code, including 2 from `-detailed-exitcode`.

`plan -json` and every other command (`apply`, `init`, `show` and so on) go straight to terraform unchanged.

## Render saved output

```bash
terraform show -json plan.tfplan | terraformat render
terraform plan -json | terraformat --format markdown render
terraformat --format json render hcp-run.log > summary.json
```

`render --detailed-exitcode` exits like `terraform plan -detailed-exitcode`:

| Exit | Meaning |
|---|---|
| 0 | No changes |
| 1 | An error diagnostic, or a plan that did not finish |
| 2 | Changes |

## Options

These go before the command, for both `render` and the wrapper.

| Option | Environment variable | Default |
|---|---|---|
| `--format table\|markdown\|json` | `TERRAFORMAT_FORMAT` | `table` |
| `--colour / --no-colour` | `NO_COLOR` turns it off | On for a terminal |
| `--output FILE` | | Standard output |
| `--terraform PATH` | `TERRAFORMAT_TERRAFORM` | `terraform` |

## Use it as a library

```python
from pathlib import Path

import terraformat

plan = terraformat.load(Path("hcp-run.log").read_text())

plan.counts[terraformat.Op.MOVE]  # 3
plan.has_changes                  # True, even when only moving
print(terraformat.to_markdown(plan))
```

- `load()` reads any form. `from_plan_json()`, `from_json_stream()` and `from_text()` read one.
- A `Plan` holds `changes`, `drift` and `diagnostics`, plus `complete`, which is False when the output stops before planning finished.
- `counts`, `counts_by_type()` and `drift_summary()` derive the numbers from those lists.
- `tally_phrase()`, `change_line()`, `change_block()` and `shown_ops()` render the pieces, for building a summary across several plans.

## JSON output

`--format json` and `Plan.to_dict()` produce:

```json
{
  "schema_version": 1,
  "source": "plan_json",
  "complete": true,
  "has_changes": true,
  "counts": {"import": 0, "add": 2, "change": 1, "replace": 1, "destroy": 2, "move": 1, "forget": 1, "read": 0},
  "changes": [
    {"address": "terraform_data.swap", "verb": "replace", "symbol": "-/+", "resource_type": "terraform_data", "moved_from": null, "importing": false}
  ],
  "drift": [],
  "diagnostics": [
    {"severity": "warning", "summary": "...", "detail": "...", "filename": "main.tf", "line": 3, "code": "...", "values": [], "count": 1}
  ]
}
```

`changes` and `drift` share a shape and sort most destructive first. `verb` is one of `delete`, `replace`, `forget_replace`, `forget`, `update`, `create`, `no-op` and `read`. `schema_version` goes up only for a change that breaks readers, and `Plan.from_dict()` refuses a version it doesn't know.

## Development

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

`tests/fixtures/terraform_data/` holds real Terraform output for one plan in all three forms, and the tests check that each form reads the same.

To release, set `version` in `pyproject.toml`, merge, then push a matching tag such as `v1.0.0`. The `Publish` workflow tests, builds and uploads to PyPI through trusted publishing.

## Licence

[The Unlicense](LICENSE).
