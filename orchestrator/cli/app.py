"""Experimental Typer CLI for the interactive terminal control layer."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from orchestrator.control import (
    build_baseline_command,
    build_experiment_command,
    get_project_paths,
    get_workspace_status,
    list_experiment_config_summaries,
    list_result_items,
    load_environment,
    open_path,
    read_experiment_config_summary,
    read_project_status,
    resolve_project_path,
    resolve_result_selector,
    run_baseline,
    run_experiment_control,
    summarize_environment,
    clean_workspace_all,
    clean_workspace_candidates,
    clean_workspace_experiments,
)
from orchestrator.control.open_artifact import OpenArtifactError
from orchestrator.control.results_browser import ResultItem
from orchestrator.control.workspace_manager import CleanupResult, WorkspaceStatus
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


def _format_bool(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return "yes" if value else "no"


def _format_list(values: list[str]) -> str:
    return ", ".join(values) if values else "unknown"


def _experiment_summary_panel(config_path: Path) -> Panel:
    summary = read_experiment_config_summary(config_path)
    text = "\n".join(
        [
            f"Config: {_display_path(summary.path)}",
            f"Experiment: {summary.name}",
            f"Description: {summary.description or 'unknown'}",
            f"Target: {summary.target_file or 'unknown'}",
            f"Baseline: {summary.baseline_run_dir or 'unknown'}",
            f"Iterations: {summary.total_iterations if summary.total_iterations is not None else 'unknown'}",
            "Mode: closed-loop optimization",
            f"Reporting: {_format_bool(summary.reporting_enabled)}",
            f"Providers: {_format_list(summary.providers)}",
            f"Models: {_format_list(summary.models)}",
            f"Status: {summary.status}",
            f"Message: {summary.message or '-'}",
        ]
    )
    return Panel(text, title="Experiment Summary", border_style="cyan")


def _format_number(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.4f}"


def _artifact_rows(item: ResultItem) -> list[tuple[str, str]]:
    artifacts = item.artifacts
    rows: list[tuple[str, str]] = []
    for label, path in (
        ("directory", artifacts.directory),
        ("summary", artifacts.summary_txt),
        ("metadata", artifacts.metadata_json),
        ("status", artifacts.status_json),
        ("metrics", artifacts.metrics_json),
        ("experiment_status", artifacts.experiment_status_json),
        ("experiment_config_snapshot", artifacts.experiment_config_snapshot_json),
        ("experiment_config_effective", artifacts.experiment_config_effective_json),
        ("closed_loop_summary", artifacts.closed_loop_summary_json),
        ("closed_loop_iterations", artifacts.closed_loop_iterations_jsonl),
        ("final_source", artifacts.final_optimized_source_dir),
        ("final_diff", artifacts.final_optimized_source_diff),
        ("report_dir", artifacts.report_dir),
        ("report_pdf", artifacts.report_pdf),
        ("report_html", artifacts.report_html),
        ("final_selection_dir", artifacts.final_selection_dir),
        ("final_selection_report", artifacts.final_selection_report),
    ):
        rows.append((label, "-" if path is None else _display_path(path)))
    return rows


def _result_detail_panel(item: ResultItem) -> Panel:
    text = "\n".join(
        [
            f"Kind: {item.kind}",
            f"Name: {item.name}",
            f"Path: {_display_path(item.path)}",
            f"Status: {item.status or 'unknown'}",
            f"Started: {item.started_at or '-'}",
            f"Finished: {item.finished_at or '-'}",
            f"Final selection speedup: {_format_number(item.final_speedup_vs_baseline)}",
            f"Final selection runtime reduction %: {_format_number(item.final_runtime_reduction_percent)}",
            f"Best iteration: {item.final_best_iteration if item.final_best_iteration is not None else '-'}",
            f"Accepted improvements: {item.accepted_improvements if item.accepted_improvements is not None else '-'}",
        ]
    )
    return Panel(text, title="Result", border_style="cyan")


def _print_result_details(item: ResultItem) -> None:
    console.print(_result_detail_panel(item))
    if item.summary_text:
        console.print(Panel(item.summary_text, title="Summary", border_style="cyan"))
    artifacts = Table(title="Artifacts", show_header=True, header_style="bold cyan")
    artifacts.add_column("Artifact")
    artifacts.add_column("Path")
    for label, path_text in _artifact_rows(item):
        artifacts.add_row(label, path_text)
    console.print(artifacts)
    if item.read_errors:
        console.print(
            Panel("\n".join(item.read_errors), title="Read Errors", border_style="red")
        )


def _artifact_path(item: ResultItem, artifact: str) -> Path | None:
    artifacts = item.artifacts
    if artifact == "directory":
        return artifacts.directory
    if artifact == "summary":
        return artifacts.summary_txt
    if artifact == "final-source":
        return artifacts.final_optimized_source_dir
    if artifact == "final-diff":
        return artifacts.final_optimized_source_diff
    if artifact == "final-selection-dir":
        return artifacts.final_selection_dir
    if artifact == "final-selection-report":
        return artifacts.final_selection_report
    if artifact == "report":
        return artifacts.report_html or artifacts.report_pdf or artifacts.report_dir
    return None


def _format_bytes(size: int) -> str:
    units = ["B", "KiB", "MiB", "GiB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def _workspace_status_table(status: WorkspaceStatus) -> Table:
    table = Table(title="Workspace Status", show_header=True, header_style="bold cyan")
    table.add_column("Item")
    table.add_column("Value")
    table.add_row("Path", _display_path(status.path))
    table.add_row("Exists", _yes_no(status.exists))
    table.add_row("Total files", str(status.total_files))
    table.add_row("Total directories", str(status.total_dirs))
    table.add_row("Total size", _format_bytes(status.total_size_bytes))
    table.add_row("Candidate workspaces", str(len(status.candidate_workspaces)))
    table.add_row("Experiment workspaces", str(len(status.experiment_workspaces)))
    table.add_row("Other entries", str(len(status.other_entries)))
    return table


def _cleanup_result_panel(result: CleanupResult) -> Panel:
    text = "\n".join(
        [
            f"Kind: {result.kind}",
            f"Deleted paths: {result.deleted_paths_count}",
            f"Deleted files: {result.deleted_files_count}",
            f"Deleted bytes estimate: {_format_bytes(result.deleted_bytes_estimate)}",
            f"Errors: {len(result.errors)}",
        ]
    )
    return Panel(text, title="Workspace Cleanup", border_style="red" if result.errors else "green")


def _run_workspace_cleanup(kind: str, yes: bool) -> None:
    if not yes and not typer.confirm(
        f"Clean workspace {kind}? This only deletes data inside workspace/ and never results/."
    ):
        console.print("Workspace cleanup cancelled.")
        return
    cleanup = {
        "candidates": clean_workspace_candidates,
        "experiments": clean_workspace_experiments,
        "all": clean_workspace_all,
    }[kind]
    result = cleanup()
    console.print(_cleanup_result_panel(result))
    if result.deleted_paths:
        table = Table(title="Deleted Paths", show_header=True, header_style="bold cyan")
        table.add_column("Path")
        for path in result.deleted_paths:
            table.add_row(_display_path(path))
        console.print(table)
    if result.errors:
        console.print(Panel("\n".join(result.errors), title="Cleanup Errors", border_style="red"))


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
def baseline_run(
    solver: str | None = typer.Option(
        None,
        "--solver",
        help="Optional solver_id from cpp/bench/*/solvers manifests.",
    ),
) -> None:
    """Run the existing baseline automation entry point."""

    paths = get_project_paths()
    command = build_baseline_command(solver)
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
        solver_id=solver,
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

    table = Table(title="Experiment Configs", show_header=True, header_style="bold cyan")
    table.add_column("Config")
    table.add_column("Experiment name")
    table.add_column("Baseline")
    table.add_column("Iterations")
    table.add_column("Reporting")
    table.add_column("Provider/model")
    table.add_column("Status")

    summaries = list_experiment_config_summaries()
    if summaries:
        for summary in summaries:
            providers = _format_list(summary.providers)
            models = _format_list(summary.models)
            status = summary.status if summary.message is None else f"{summary.status}: {summary.message}"
            table.add_row(
                summary.path.name,
                summary.name,
                summary.baseline_run_dir or "unknown",
                str(summary.total_iterations) if summary.total_iterations is not None else "unknown",
                _format_bool(summary.reporting_enabled),
                f"{providers} / {models}",
                status,
            )
    else:
        paths = get_project_paths()
        table.add_row(
            "none",
            f"No JSON configs found under {_display_path(paths.experiments_config)}",
            "unknown",
            "unknown",
            "missing",
        )
    console.print(table)


@experiment_app.command("run")
def experiment_run(
    config: Path = typer.Option(..., "--config", help="Experiment config JSON path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Run experiment runner in dry-run mode."),
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation for real experiment runs."),
) -> None:
    """Run or dry-run an experiment config via the existing experiment runner."""

    config_path = resolve_project_path(config)
    if not config_path.is_file():
        raise typer.BadParameter(f"Config path does not exist: {config_path}")

    console.print(_experiment_summary_panel(config_path))
    command = build_experiment_command(config_path, dry_run=dry_run)
    console.print(
        Panel(
            f"Command: {' '.join(command)}\n"
            f"Mode: {'dry-run' if dry_run else 'real run'}",
            title="Experiment Launch",
            border_style="cyan",
        )
    )
    if not dry_run:
        console.print(
            Panel(
                "This may use paid LLM API calls. API keys are read from the process environment or .env.local.",
                title="Confirmation Required",
                border_style="yellow",
            )
        )
        if not yes and not typer.confirm("Continue with the real experiment run?"):
            console.print("Experiment run cancelled.")
            return

    def print_stdout(line: str) -> None:
        console.print(line)

    def print_stderr(line: str) -> None:
        console.print(line, style="red")

    result = run_experiment_control(
        config_path,
        dry_run=dry_run,
        on_stdout=print_stdout,
        on_stderr=print_stderr,
    )
    duration = (
        "n/a"
        if result.process_result is None
        else f"{result.process_result.duration_seconds:.3f}s"
    )
    latest_dir = (
        "-"
        if result.latest_experiment_dir is None
        else _display_path(result.latest_experiment_dir)
    )
    console.print(
        Panel(
            f"Status: {result.status}\n"
            f"Exit code: {result.exit_code if result.exit_code is not None else 'n/a'}\n"
            f"Duration: {duration}\n"
            f"Latest experiment directory: {latest_dir}\n"
            f"Message: {result.message}\n\n"
            "Hint: use `python -m orchestrator.cli.app results latest` to inspect recent runs.",
            title="Experiment Result",
            border_style="green" if result.status == "success" else "red",
        )
    )
    if result.status != "success":
        raise typer.Exit(1)


@results_app.command("list")
def results_list() -> None:
    """List saved runs and experiments."""

    items = list_result_items()
    table = Table(title="Results", show_header=True, header_style="bold cyan")
    table.add_column("Kind")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Started")
    table.add_column("Finished")
    table.add_column("Speedup")
    table.add_column("Best iteration")
    table.add_column("Path")
    if not items:
        table.add_row("none", "No results found", "-", "-", "-", "-", "-", "-")
    for item in items:
        table.add_row(
            item.kind,
            item.name,
            item.status or "unknown",
            item.started_at or "-",
            item.finished_at or "-",
            _format_number(item.final_speedup_vs_baseline),
            str(item.final_best_iteration) if item.final_best_iteration is not None else "-",
            _display_path(item.path),
        )
    console.print(table)


@results_app.command("latest")
def results_latest() -> None:
    """Show the latest saved result."""

    results_show("latest")


@results_app.command("show")
def results_show(selector: str) -> None:
    """Show details for a saved result."""

    item = resolve_result_selector(selector)
    if item is None:
        console.print(Panel(f"Result not found or ambiguous: {selector}", title="Results", border_style="red"))
        raise typer.Exit(1)
    _print_result_details(item)


@results_app.command("open")
def results_open(
    selector: str,
    artifact: str = typer.Option(
        "directory",
        "--artifact",
        help="Artifact to open: directory, summary, final-source, final-diff, final-selection-dir, final-selection-report, report.",
    ),
) -> None:
    """Open a result directory or artifact in the OS file explorer."""

    item = resolve_result_selector(selector)
    if item is None:
        console.print(Panel(f"Result not found or ambiguous: {selector}", title="Results", border_style="red"))
        raise typer.Exit(1)
    path = _artifact_path(item, artifact)
    if path is None:
        console.print(Panel(f"Artifact is not available: {artifact}", title="Results", border_style="red"))
        raise typer.Exit(1)
    try:
        open_path(path)
    except OpenArtifactError as exc:
        console.print(Panel(str(exc), title="Results", border_style="red"))
        raise typer.Exit(1) from exc
    console.print(f"Opened: {_display_path(path)}")


@workspace_app.command("status")
def workspace_status() -> None:
    """Show workspace presence, size, and temporary workspace counts."""

    console.print(Panel("Workspace cleanup only affects workspace/ and never results/.", title="Workspace", border_style="cyan"))
    console.print(_workspace_status_table(get_workspace_status()))


@workspace_app.command("clean-candidates")
def workspace_clean_candidates(
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation."),
) -> None:
    """Delete candidate workspaces under workspace/candidates/."""

    _run_workspace_cleanup("candidates", yes)


@workspace_app.command("clean-experiments")
def workspace_clean_experiments(
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation."),
) -> None:
    """Delete experiment workspaces under workspace/experiments/."""

    _run_workspace_cleanup("experiments", yes)


@workspace_app.command("clean-all")
def workspace_clean_all(
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation."),
) -> None:
    """Delete temporary entries inside workspace/ while preserving workspace/.gitkeep."""

    _run_workspace_cleanup("all", yes)


app.add_typer(baseline_app, name="baseline")
app.add_typer(experiment_app, name="experiment")
app.add_typer(results_app, name="results")
app.add_typer(workspace_app, name="workspace")


if __name__ == "__main__":
    app()
