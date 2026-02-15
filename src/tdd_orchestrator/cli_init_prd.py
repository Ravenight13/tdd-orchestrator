"""CLI init-prd command for TDD Orchestrator.

Scaffolds an opinionated PRD template file aligned with what the
decomposition parser expects, so users don't have to guess the format.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import click

from .prd_template import generate_prd_template


def _slugify(name: str) -> str:
    """Convert a feature name to a filename-safe slug.

    Example: "User Authentication" -> "user_authentication"
    """
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")


def _name_from_stem(stem: str) -> str:
    """Derive a human-readable name from a filename stem.

    Example: "auth_spec" -> "Auth Spec"
    """
    # Remove common suffixes
    clean = re.sub(r"_spec$", "", stem)
    return clean.replace("_", " ").title()


@click.command("init-prd")
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output file path (default: <name>_spec.txt in cwd)",
)
@click.option(
    "--name",
    "-n",
    default=None,
    help="Feature name for the template title",
)
@click.option(
    "--phases",
    type=int,
    default=3,
    help="Number of phase/cycle stubs (default: 3)",
)
@click.option(
    "--with-module-api",
    is_flag=True,
    help="Include MODULE API SPECIFICATION section",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing file",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print to stdout, don't write file",
)
def init_prd_command(
    output: str | None,
    name: str | None,
    phases: int,
    with_module_api: bool,
    force: bool,
    dry_run: bool,
) -> None:
    """Scaffold an opinionated PRD template for TDD decomposition.

    Generates a template file with all sections the decomposition
    parser expects: FR, NFR, AC, TDD cycles, module structure, and
    dependency changes.
    """
    # Resolve name and output path
    if name and not output:
        output = f"{_slugify(name)}_spec.txt"
    elif output and not name:
        name = _name_from_stem(Path(output).stem)
    elif not name and not output:
        click.echo("Error: provide --name or --output (or both)", err=True)
        sys.exit(1)

    # name is guaranteed non-None after the above checks
    assert name is not None
    assert output is not None

    out_path = Path(output)

    # Ensure .txt extension
    if not out_path.suffix:
        out_path = out_path.with_suffix(".txt")

    template = generate_prd_template(
        name,
        phases=phases,
        with_module_api=with_module_api,
    )

    if dry_run:
        click.echo(template)
        return

    if out_path.exists() and not force:
        click.echo(
            f"Error: {out_path} already exists. Use --force to overwrite.",
            err=True,
        )
        sys.exit(1)

    out_path.write_text(template, encoding="utf-8")
    click.echo(f"Created PRD template: {out_path}")
    click.echo("")
    click.echo("Next steps:")
    click.echo(f"  1. Edit {out_path} with your feature requirements")
    click.echo(f"  2. tdd-orchestrator ingest --prd {out_path}")
