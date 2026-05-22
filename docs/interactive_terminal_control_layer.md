# Interactive Terminal Control Layer

The Interactive Terminal Control Layer provides a Typer/Rich CLI and Textual TUI for operating the bachelor thesis prototype without reimplementing the optimization pipeline. It launches existing entry points, reads existing artifacts, and reports status.

## Setup

Install Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

Create local environment settings from the committed template:

```powershell
copy .env.example .env.local
```

Keep local paths and API keys in `.env.local`. Secrets are masked in CLI/TUI diagnostics.

## Commands

Diagnostics:

```powershell
py -m orchestrator.cli.app doctor
py -m orchestrator.cli.app tui
```

Baseline:

```powershell
py -m orchestrator.cli.app baseline run
```

Experiments:

```powershell
py -m orchestrator.cli.app experiment list
py -m orchestrator.cli.app experiment run --config configs/experiments/<file>.json --dry-run
py -m orchestrator.cli.app experiment run --config configs/experiments/<file>.json --yes
```

Results:

```powershell
py -m orchestrator.cli.app results list
py -m orchestrator.cli.app results latest
py -m orchestrator.cli.app results show latest
py -m orchestrator.cli.app results open latest
```

Workspace:

```powershell
py -m orchestrator.cli.app workspace status
py -m orchestrator.cli.app workspace clean-candidates --yes
py -m orchestrator.cli.app workspace clean-experiments --yes
py -m orchestrator.cli.app workspace clean-all --yes
```

## TUI

Launch the TUI:

```powershell
py -m orchestrator.cli.app tui
```

Available screens include Doctor, Environment, Run Baseline, Run Experiment, Browse Results, Workspace, and Help. Use `Esc` to go back from secondary screens and `Ctrl+Q` to quit.

While a baseline or experiment run is active, the TUI keeps the current screen open and blocks Back, `Esc`, and `Ctrl+Q` until the run finishes. Cancellation is not implemented yet.

## Safety Guarantees

- The control layer does not reimplement baseline or experiment logic.
- Baseline and experiment actions launch existing Python entry points.
- The results browser is read-only and does not recalculate metrics, decisions, or reports.
- Workspace cleanup only deletes entries inside `workspace/`; it does not delete `results/`.
- API keys and other secrets are masked in displays.
- The main `cpp/` source tree is not modified automatically by the control layer.

## TUI debug log

The TUI may write diagnostic messages to `workspace/tui_debug.log`. This file is local and debug-only. Remove it manually or via:

```powershell
py -m orchestrator.cli.app workspace clean-all --yes
```

It is not required for normal operation and is safe to delete.
