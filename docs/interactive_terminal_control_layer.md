# Interactive Terminal Control Layer

The Interactive Terminal Control Layer provides a Typer/Rich CLI and Textual
TUI for operating the optimization pipeline. It launches existing entry points,
reads existing artifacts, and reports status — it does **not** reimplement
baseline or experiment logic.

Available screens through the TUI include Doctor, Environment, Run Baseline,
Run Experiment, Browse Results, Workspace, Config Builder, Active Run (live
output), and Help. Use `Esc` to go back and `Ctrl+Q` to quit.

For the full command reference and safety guarantees, see
[docs/usage.md](usage.md).
