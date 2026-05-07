"""CLI entrypoint.

    extractor run --corpus <path>           # extract everything
    extractor run --corpus <path> --output-dir <path>
"""

from __future__ import annotations

from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from extractor.llm import get_provider
from extractor.pipeline import run_corpus

console = Console()


@click.group()
def main() -> None:
    """Stackpoint loan-document extractor."""
    load_dotenv()
    load_dotenv(_repo_root() / ".env")


@main.command("run")
@click.option(
    "--corpus",
    "corpus_path",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Path to the document corpus (parent of borrower folders).",
)
@click.option(
    "--output-dir",
    "output_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Where to write JSON output. Default: apps/web/data/output/",
)
@click.option(
    "--provider",
    default=None,
    help="LLM provider (claude|openai). Default: $LLM_PROVIDER or claude.",
)
@click.option(
    "--model",
    default=None,
    help="Model ID. Default: $LLM_MODEL or claude-opus-4-7.",
)
def run_cmd(
    corpus_path: Path,
    output_dir: Path | None,
    provider: str | None,
    model: str | None,
) -> None:
    """Extract structured data from every borrower folder under <corpus>."""
    if output_dir is None:
        output_dir = _repo_root() / "apps" / "web" / "data" / "output"

    llm = get_provider(name=provider, model=model)
    console.print(
        f"[bold]Running extraction[/bold] — provider={llm.name} model={llm.model}"
    )
    console.print(f"  corpus:  {corpus_path}")
    console.print(f"  output:  {output_dir}\n")

    results = run_corpus(corpus_path, llm, output_dir=output_dir)

    table = Table(title="Extraction summary")
    table.add_column("borrower", style="cyan")
    table.add_column("docs")
    table.add_column("flags", justify="right")
    table.add_column("seconds", justify="right")
    table.add_column("output", style="dim")
    for borrower, path in results:
        table.add_row(
            borrower.id,
            str(len(borrower.source_documents)),
            str(len(borrower.flags)),
            f"{borrower.extraction_meta.duration_seconds:.1f}",
            str(path.relative_to(_repo_root())),
        )
    console.print(table)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3].parent


if __name__ == "__main__":
    main()
