# terraformat

A wrapper for the Terraform CLI that provides a formatted plan summary.

## Overview

**terraformat** is a command-line tool designed to improve the readability of `terraform plan` outputs. It runs your Terraform plan and summarizes the planned resource changes (create, update, destroy) in a color-coded, tabular format. This helps teams more quickly and safely review infrastructure changes before applying them.

## Features

- Runs any `terraform` command, but enhances `terraform plan` with a summary table
- Color-coded output for quick identification of create (green), update (yellow), and destroy (red) actions
- Parses complex Terraform resource addresses, including those in modules
- Integrates seamlessly into existing Terraform workflows

## Installation

```bash
pip install .
pip install git+https://github.com/henryupton/terraformat.git
```

## Requirements
* Python 3.7+
* Terraform installed and available in your PATH

### Python dependencies (installed automatically):
* click
* tabulate

## Usage

After installation, you can use terraformat as a drop-in replacement for terraform. All commands are passed through to Terraform, but plan will be summarized:

```bash
terraformat plan [ARGS...]
```

#### Example output
```bash
🚀 Running 'terraform plan'...
--- Original Terraform Output ---
[standard terraform plan output here]

==================================================
📊 Terraformat Summary
==================================================
+----------------+---------+---------+----------+
| Resource Type  | Create  | Update  | Destroy  |
+================+=========+=========+==========+
| aws_instance   |   1     |   0     |    1     |
| local_file     |   1     |   0     |    0     |
| random_pet     |   0     |   1     |    0     |
+----------------+---------+---------+----------+
| Total          |   2     |   1     |    1     |
+----------------+---------+---------+----------+
```

If you run other Terraform commands, they’re just passed through unchanged: