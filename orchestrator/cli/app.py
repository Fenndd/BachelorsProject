"""Experimental Typer CLI for the interactive terminal control layer."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from orchestrator.control import (
    build_baseline_command,
    get_project_paths,
    load_environment,
    read_project_status,
    resolve_project_path,
    run_baseline,
    summarize_environment,
)
from orchestrator.control import placeholders


app = typer.Typer(
    help="Experimental control layer for the Bachelor Project optimizer.",
    no_args_is_help=True,
)
baseline_app = typer.Typer(help="Baseline controls.")
experiment_app = typer.Typer(help="Experiment controls.")
results_app = typer.Typer(help="Results controls.")
workspace_app = typer.Typer(help="Workspace controls.")
console = Console()


def _yes_no(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return "yes" if value else "no"


def _display_path(path: Path) -> str:
    paths = get_project_paths()
    try:
        return path.resolve().relative_to(paths.repo_root).as_posix()
    except ValueError:
        return str(path)


def _directory_status_table() -> Table:
    status = read_project_status()
    table = Table(title="Project Status", show_header=True, header_style="bold cyan")
    table.add_column("Item")
    table.add_column("Value")
    table.add_row("Repository root", str(status.repo_root))
    table.add_row("Git available", _yes_no(status.git_available))
    table.add_row("Git branch", status.git_branch or "unknown")
    table.add_row("Dirty worktree", _yes_no(status.dirty_worktree))
    for name, exists in status.directories.items():
        table.add_row(f"{name}/ exists", _yes_no(exists))
    return table


def _environment_status_table() -> Table:
    statuses = load_environment()
    table = Table(title="Environment Status", show_header=True, header_style="bold cyan")
    table.add_column("Variable")
    table.add_column("Status")
    table.add_column("Source")
    table.add_column("Value")
    table.add_column("Message")
    for status in statuses:
        table.add_row(
            status.name,
            status.status,
            status.source,
            status.display_value or "-",
            status.message,
        )
    return table


def _selected_environment_table(names: set[str]) -> Table:
    statuses = [status for status in load_environment() if status.name in names]
    table = Table(title="Baseline Environment", show_header=True, header_style="bold cyan")
    table.add_column("Variable")
    table.add_column("Status")
    table.add_column("Source")
    table.add_column("Value")
    table.add_column("Message")
    for status in statuses:
        table.add_row(
            status.name,
            status.status,
            status.source,
            status.display_value or "-",
            status.message,
        )
    return table


def _iter_json_configs() -> Iterable[Path]:
    paths = get_project_paths()
    if not paths.experiments_config.is_dir():
        return []
    return sorted(paths.experiments_config.glob("*.json"))


def _latest_directories() -> list[tuple[str, Path]]:
    paths = get_project_paths()
    candidates: list[tuple[str, Path]] = []
    for label, root in (("run", paths.result_runs), ("experiment", paths.result_experiments)):
        if root.is_dir():
            candidates.extend((label, child) for child in root.iterdir() if child.is_dir())
    return sorted(candidates, key=lambda item: item[1].stat().st_mtime, reverse=True)


@app.command()
def tui() -> None:
    """Launch the Textual terminal UI."""

    from orchestrator.tui.app import OptimizerTuiApp

    OptimizerTuiApp().run()


@app.command()
def doctor() -> None:
    """Show basic project health information."""

    statuses = load_environment()
    summary = summarize_environment(statuses)
    note = (
        f"{placeholders.DOCTOR}\n\n"
        f"Environment: {summary.label}; API keys: {summary.api_keys_label}.\n"
        "Full build/run checks will be added later."
    )
    console.print(Panel(note, title="Doctor", border_style="cyan"))
    console.print(_directory_status_table())
    if not summary.env_local_exists:
        console.print(
            Panel(
                ".env.local not found. Copy .env.example to .env.local and fill local paths/API keys.",
                title="Local Environment",
                border_style="yellow",
            )
        )
    console.print(_environment_status_table())


@baseline_app.command("run")
def baseline_run() -> None:
    """Run the existing baseline automation entry point."""

    paths = get_project_paths()
    command = build_baseline_command()
    command_text = " ".join(command)
    statuses = load_environment()
    summary = summarize_environment(statuses)
    console.print(
        Panel(
            "Launching the existing baseline automation entry point.\n"
            f"Command: {command_text}\n"
            f"Working directory: {paths.repo_root}\n"
            f"Environment: {summary.label}",
            title="Baseline Run",
            border_style="cyan",
        )
    )
    console.print(
        _selected_environment_table(
            {
                "EIGEN3_INCLUDE_DIR",
                "CMAKE_EXE",
                "CMAKE_GENERATOR",
                "CMAKE_CXX_COMPILER",
                "CMAKE_MAKE_PROGRAM",
                "BENCHMARK_CMAKE_BUILD_TYPE",
            }
        )
    )

    def print_stdout(line: str) -> None:
        console.print(line)

    def print_stderr(line: str) -> None:
        console.print(line, style="red")

    result = run_baseline(
        paths.repo_root,
        on_stdout=print_stdout,
        on_stderr=print_stderr,
    )

    duration = (
        "n/a"
        if result.process_result is None
        else f"{result.process_result.duration_seconds:.3f}s"
    )
    latest_run = "-" if result.latest_run_dir is None else _display_path(result.latest_run_dir)
    console.print(
        Panel(
            f"Status: {result.status}\n"
            f"Exit code: {result.exit_code if result.exit_code is not None else 'n/a'}\n"
            f"Duration: {duration}\n"
            f"Latest run directory: {latest_run}\n"
            f"Message: {result.message}\n\n"
            "Hint: use `python -m orchestrator.cli.app results latest` to inspect recent runs.",
            title="Baseline Result",
            border_style="green" if result.status == "success" else "red",
        )
    )
    if result.status != "success":
        raise typer.Exit(1)


@experiment_app.command("list")
def experiment_list() -> None:
    """List experiment JSON configs."""

    paths = get_project_paths()
    table = Table(title="Experiment Configs", show_header=True, header_style="bold cyan")
    table.add_column("Config")
    table.add_column("Path")

    configs = list(_iter_json_configs())
    if configs:
        for config in configs:
            table.add_row(config.stem, _display_path(config))
    else:
        table.add_row("none", f"No JSON configs found under {_display_path(paths.experiments_config)}")
    console.print(table)


@experiment_app.command("run")
def experiment_run(
    config: Path = typer.Option(..., "--config", help="Experiment config JSON path."),
) -> None:
    """Validate an experiment config path, then show integration placeholder."""

    config_path = resolve_project_path(config)
    if not config_path.is_file():
        raise typer.BadParameter(f"Config path does not exist: {config_path}")

    message = f"{placeholders.EXPERIMENT_RUN}\n\nValidated config: {_display_path(config_path)}"
    console.print(Panel(message, title="Experiment Run", border_style="yellow"))


@results_app.command("latest")
def results_latest() -> None:
    """Show latest result directories when available."""

    latest = _latest_directories()
    if not latest:
        console.print(Panel("No result directories found yet.", title="Latest Results"))
        return

    table = Table(title="Latest Results", show_header=True, header_style="bold cyan")
    table.add_column("Kind")
    table.add_column("Path")
    table.add_column("Modified")
    for kind, path in latest[:10]:
        modified = path.stat().st_mtime
        table.add_row(kind, _display_path(path), f"{modified:.0f}")
    console.print(table)


@workspace_app.command("status")
def workspace_status() -> None:
    """Show basic workspace presence and file counts."""

    paths = get_project_paths()
    workspace = paths.workspace
    table = Table(title="Workspace Status", show_header=True, header_style="bold cyan")
    table.add_column("Item")
    table.add_column("Value")
    table.add_row("Path", _display_path(workspace))
    table.add_row("Exists", _yes_no(workspace.is_dir()))

    if workspace.is_dir():
        direct_files = sum(1 for child in workspace.iterdir() if child.is_file())
        direct_dirs = sum(1 for child in workspace.iterdir() if child.is_dir())
        all_files = sum(1 for child in workspace.rglob("*") if child.is_file())
        all_dirs = sum(1 for child in workspace.rglob("*") if child.is_dir())
        table.add_row("Direct files", str(direct_files))
        table.add_row("Direct directories", str(direct_dirs))
        table.add_row("Total files", str(all_files))
        table.add_row("Total directories", str(all_dirs))

    console.print(Panel(placeholders.WORKSPACE, title="Workspace", border_style="cyan"))
    console.print(table)


app.add_typer(baseline_app, name="baseline")
app.add_typer(experiment_app, name="experiment")
app.add_typer(results_app, name="results")
app.add_typer(workspace_app, name="workspace")


if __name__ == "__main__":
    app()
