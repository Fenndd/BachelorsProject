"""Config builder screen for interactive experiment JSON creation."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, RichLog, Select, Static, Switch, TextArea

from orchestrator.control import get_project_paths
from orchestrator.control import list_run_items
from orchestrator.experiments.experiment_config import (
    ExperimentConfigError,
    load_experiment_config,
)
from orchestrator.shared.io.json_io import read_json


def _read_solver_manifest_options() -> list[tuple[str, str, str | None, list[str] | None]]:
    """Read solver manifests from ``cpp/bench/*/solvers/*.json``.

    Returns list of tuples: (display_label, solver_id, default_target_file, default_allowed_files)
    """
    paths = get_project_paths()
    manifest_dir = paths.cpp / "bench"
    pattern = "*/solvers/*.json"
    options: list[tuple[str, str, str | None, list[str] | None]] = []
    for manifest_path in sorted(manifest_dir.glob(pattern)):
        try:
            data = read_json(manifest_path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        solver_id = data.get("solver_id")
        if not isinstance(solver_id, str) or not solver_id:
            continue
        display_name = data.get("display_name")
        if not isinstance(display_name, str):
            display_name = solver_id
        default_target = data.get("default_target_file")
        if not isinstance(default_target, str):
            default_target = None
        default_allowed = data.get("default_allowed_files")
        if not (isinstance(default_allowed, list) and all(isinstance(f, str) for f in default_allowed)):
            default_allowed = [default_target] if default_target else None
        options.append((f"{display_name} ({solver_id})", solver_id, default_target, default_allowed))
    return options


def _discover_llm_configs() -> list[tuple[str, str]]:
    """Discover LLM config files under ``configs/llm_*.json``.

    Returns list of (display_label, repo_relative_path).
    """
    paths = get_project_paths()
    options: list[tuple[str, str]] = []
    for llm_path in sorted(paths.configs.glob("llm_*.json")):
        rel = str(llm_path.relative_to(paths.repo_root)).replace("\\", "/")
        options.append((rel, rel))
    return options


def _discover_baseline_runs() -> list[tuple[str, str]]:
    """Discover baseline runs from ``results/runs/``.

    Returns list of (display_label, repo_relative_dir).
    """
    paths = get_project_paths()
    try:
        run_items = list_run_items(paths.repo_root)
    except Exception:
        run_items = []
    options: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in run_items:
        try:
            rel = str(item.path.relative_to(paths.repo_root)).replace("\\", "/")
        except ValueError:
            continue
        if rel in seen:
            continue
        seen.add(rel)
        label = f"{rel} [{item.status or '?'}]"
        options.append((label, rel))
    if not options:
        options.append(("No runs found -- type path manually", ""))
    return options


def _safe_name(name: str) -> str:
    """Normalize *name* to a lowercase filesystem-safe stem."""
    if not name or not name.strip():
        return "experiment_config"
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", name.strip())
    safe = re.sub(r"_+", "_", safe)
    safe = safe.strip("_").lower() or "experiment_config"
    return safe


class ConfigBuilderScreen(Screen[None]):
    BINDINGS = [("escape", "request_back", "Back")]

    DEFAULT_CSS = """
    #builder-form {
        padding: 0 1;
    }
    .field-label {
        margin-top: 1;
        color: #f8fafc;
        text-style: bold;
    }
    .field-widget {
        margin-bottom: 1;
    }
    #build-errors {
        height: 6;
        margin-top: 1;
        background: #2f3136;
        color: #f8fafc;
    }
    #builder-buttons {
        layout: grid;
        grid-size: 3;
        grid-gutter: 1;
        margin-top: 1;
        margin-bottom: 1;
    }
    .builder-button {
        width: 100%;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._solver_options = _read_solver_manifest_options()
        self._llm_configs = _discover_llm_configs()
        self._baseline_runs = _discover_baseline_runs()
        self._templates: list[Path] = self._discover_templates()
        self._local_configs: list[Path] = self._discover_local()

    def _discover_templates(self) -> list[Path]:
        paths = get_project_paths()
        tmpl_dir = paths.experiments_config / "templates"
        if not tmpl_dir.is_dir():
            return []
        return sorted(tmpl_dir.glob("*.template.json"))

    def _discover_local(self) -> list[Path]:
        paths = get_project_paths()
        local_dir = paths.experiments_config / "local"
        if not local_dir.is_dir():
            return []
        return sorted(local_dir.glob("*.json"))

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="main"):
            yield Static("Build Experiment Config", classes="title")
            yield Static("Fill in the form below and save to configs/experiments/local/", classes="subtitle")

            with VerticalScroll(id="builder-form"):
                yield Static("Experiment", classes="field-label")
                yield Input(
                    placeholder="experiment_name",
                    id="experiment_name",
                    classes="field-widget",
                )
                yield Input(
                    placeholder="description (optional)",
                    id="description",
                    classes="field-widget",
                )

                yield Static("Algorithm / Target File", classes="field-label")
                algo_opts: list[tuple[str, str]] = [
                    ("-- select algorithm --", "")
                ] + [(label, sid) for label, sid, _, _ in self._solver_options]
                yield Select(
                    algo_opts,
                    id="algorithm",
                    classes="field-widget",
                )
                yield Input(
                    placeholder="target_file",
                    id="target_file",
                    classes="field-widget",
                )
                yield Static("optimization_scope.allowed_files (one per line)", classes="field-label")
                yield TextArea(
                    id="allowed_files",
                    classes="field-widget",
                )

                yield Static("Baseline Run", classes="field-label")
                run_opts: list[tuple[str, str]] = self._baseline_runs[:]
                if run_opts and run_opts[-1][0] != "No runs found -- type path manually":
                    run_opts.append(("-- custom path --", "__custom__"))
                yield Select(
                    run_opts,
                    id="baseline_run_sel",
                    classes="field-widget",
                )
                yield Input(
                    placeholder="results/runs/... (custom path)",
                    id="baseline_run_dir",
                    classes="field-widget",
                )

                yield Static("Candidate Generation", classes="field-label")
                yield Input(
                    value="120000",
                    placeholder="max_source_chars",
                    id="max_source_chars",
                    classes="field-widget",
                )

                yield Static("Reporting", classes="field-label")
                with Horizontal(id="reporting-format-row", classes="field-widget"):
                    yield Static("HTML:")
                    yield Switch(id="reporting_html", value=True)
                    yield Static(" PDF:")
                    yield Switch(id="reporting_pdf", value=False)
                yield Select(
                    [
                        ("auto", "auto"),
                        ("weasyprint", "weasyprint"),
                        ("playwright", "playwright"),
                    ],
                    id="reporting_renderer",
                    classes="field-widget",
                )
                with Horizontal(id="reporting-fail-row", classes="field-widget"):
                    yield Static("fail_on_error:")
                    yield Switch(id="reporting_fail_on_error", value=False)

                yield Static("Variant", classes="field-label")
                yield Input(
                    placeholder="variant_id (auto-generated if empty)",
                    id="variant_id",
                    classes="field-widget",
                )
                yield Input(
                    placeholder="variant description (optional)",
                    id="variant_description",
                    classes="field-widget",
                )
                llm_opts: list[tuple[str, str]] = [("-- select LLM config --", "")] + self._llm_configs
                yield Select(
                    llm_opts,
                    id="variant_llm_config",
                    classes="field-widget",
                )
                yield Input(
                    value="3",
                    placeholder="iterations",
                    id="iterations",
                    classes="field-widget",
                )
                yield Static("additional_context (optional)", classes="field-label")
                yield TextArea(
                    id="additional_context",
                    classes="field-widget",
                )

                yield Static("LLM Overrides (optional, leave empty to use LLM config defaults)", classes="field-label")
                yield Select(
                    [
                        ("(use LLM config default)", ""),
                        ("deepseek", "deepseek"),
                        ("mock", "mock"),
                        ("openai", "openai"),
                        ("anthropic", "anthropic"),
                    ],
                    id="llm_provider_override",
                    classes="field-widget",
                )
                yield Input(
                    placeholder="model override (optional)",
                    id="llm_model_override",
                    classes="field-widget",
                )
                yield Input(
                    placeholder="max_tokens override (optional, e.g. 4096)",
                    id="llm_max_tokens_override",
                    classes="field-widget",
                )
                with Horizontal(id="thinking-enabled-row", classes="field-widget"):
                    yield Static("thinking.enabled:")
                    yield Switch(id="thinking_enabled", value=False)
                yield Select(
                    [
                        ("(no override)", ""),
                        ("low", "low"),
                        ("medium", "medium"),
                        ("high", "high"),
                    ],
                    id="thinking_effort",
                    classes="field-widget",
                )

            yield RichLog(id="build-errors", classes="panel", wrap=True, highlight=True)

            with Horizontal(id="builder-buttons"):
                yield Button("Validate", id="btn-validate", classes="builder-button")
                yield Button("Save to local/", id="btn-save", classes="builder-button")
                yield Button("Save & Run", id="btn-save-run", classes="builder-button")
            with Horizontal(id="builder-buttons-extra"):
                yield Button("Load Template", id="btn-load-template", classes="builder-button")
                yield Button("Load Local", id="btn-load-local", classes="builder-button")
                yield Button("Back", id="btn-back", classes="builder-button")

        yield Footer()

    def on_mount(self) -> None:
        self._log("Config builder ready.")
        if not self._solver_options:
            self._log("[warning] No solver manifests found under cpp/bench/*/solvers/")
        if not self._llm_configs:
            self._log("[warning] No LLM configs found under configs/llm_*.json")
        self._on_algorithm_changed()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "algorithm":
            self._on_algorithm_changed()

    def _on_algorithm_changed(self) -> None:
        select = self.query_one("#algorithm", Select)
        selected = select.value
        if not selected or selected == Select.BLANK:
            return
        if not isinstance(selected, str):
            return
        for label, solver_id, target_file, allowed_files in self._solver_options:
            if solver_id == selected:
                if target_file:
                    self.query_one("#target_file", Input).value = target_file
                if allowed_files:
                    textarea = self.query_one("#allowed_files", TextArea)
                    textarea.clear()
                    textarea.insert("\n".join(allowed_files))
                return

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "btn-back":
            self.app.pop_screen()
        elif btn_id == "btn-validate":
            self._validate()
        elif btn_id == "btn-save":
            self._save_to_local()
        elif btn_id == "btn-save-run":
            self._save_and_run()
        elif btn_id == "btn-load-template":
            self._load_template()
        elif btn_id == "btn-load-local":
            self._load_local()

    def action_request_back(self) -> None:
        self.app.pop_screen()

    def _log(self, message: str) -> None:
        self.query_one("#build-errors", RichLog).write(message)

    def _clear_log(self) -> None:
        self.query_one("#build-errors", RichLog).clear()

    def _get_baseline_run_dir(self) -> str:
        sel = self.query_one("#baseline_run_sel", Select)
        if isinstance(sel.value, str) and sel.value and sel.value != "__custom__":
            return sel.value
        return self.query_one("#baseline_run_dir", Input).value.strip()

    def _build_payload(self) -> dict[str, Any]:
        allowed_files_text = self.query_one("#allowed_files", TextArea).text
        allowed_files = [line.strip() for line in allowed_files_text.splitlines() if line.strip()]

        formats: list[str] = []
        if self.query_one("#reporting_html", Switch).value:
            formats.append("html")
        if self.query_one("#reporting_pdf", Switch).value:
            formats.append("pdf")
        if not formats:
            formats = ["html"]

        renderer = self.query_one("#reporting_renderer", Select).value
        if not isinstance(renderer, str) or renderer not in ("auto", "weasyprint", "playwright"):
            renderer = "auto"

        fail_on_error = bool(self.query_one("#reporting_fail_on_error", Switch).value)
        reporting_enabled = len(formats) > 0

        llm_overrides: dict[str, Any] | None = None
        override_provider = self.query_one("#llm_provider_override", Select).value
        override_model = self.query_one("#llm_model_override", Input).value.strip()
        override_max_tokens_str = self.query_one("#llm_max_tokens_override", Input).value.strip()
        override_thinking_enabled = self.query_one("#thinking_enabled", Switch).value
        override_thinking_effort = self.query_one("#thinking_effort", Select).value

        has_overrides = False
        override_dict: dict[str, Any] = {}

        if isinstance(override_provider, str) and override_provider:
            override_dict["provider"] = override_provider
            has_overrides = True
        if override_model:
            override_dict["model"] = override_model
            has_overrides = True
        if override_max_tokens_str:
            try:
                override_dict["max_tokens"] = int(override_max_tokens_str)
                has_overrides = True
            except (ValueError, TypeError):
                pass

        thinking_dict: dict[str, Any] = {}
        if bool(override_thinking_enabled):
            thinking_dict["enabled"] = True
        if isinstance(override_thinking_effort, str) and override_thinking_effort:
            thinking_dict["effort"] = override_thinking_effort
        if thinking_dict:
            override_dict["thinking"] = thinking_dict
            has_overrides = True

        if has_overrides:
            llm_overrides = override_dict

        variant_id = self.query_one("#variant_id", Input).value.strip()
        if not variant_id:
            variant_id = "default"

        iterations_str = self.query_one("#iterations", Input).value.strip()
        try:
            iterations = int(iterations_str)
        except (ValueError, TypeError):
            iterations = 0

        max_chars_str = self.query_one("#max_source_chars", Input).value.strip()
        try:
            max_source_chars = int(max_chars_str)
        except (ValueError, TypeError):
            max_source_chars = 0

        additional_ctx = self.query_one("#additional_context", TextArea).text.strip() or None

        solver_val = self.query_one("#algorithm", Select).value
        solver_id = solver_val if isinstance(solver_val, str) and solver_val else None

        payload: dict[str, Any] = {
            "experiment_name": self.query_one("#experiment_name", Input).value.strip(),
            "description": self.query_one("#description", Input).value.strip() or None,
            "solver_id": solver_id,
            "target_file": self.query_one("#target_file", Input).value.strip(),
            "baseline_run_dir": self._get_baseline_run_dir(),
            "candidate_generation": {
                "max_source_chars": max_source_chars,
            },
            "optimization_scope": {
                "allowed_files": allowed_files,
            },
            "reporting": {
                "enabled": reporting_enabled,
                "formats": formats,
                "renderer": renderer,
                "fail_on_error": fail_on_error,
            },
            "variants": [
                {
                    "variant_id": variant_id,
                    "description": self.query_one("#variant_description", Input).value.strip() or None,
                    "llm_config": (
                        self.query_one("#variant_llm_config", Select).value
                        if isinstance(self.query_one("#variant_llm_config", Select).value, str)
                        else ""
                    ),
                    "llm_overrides": llm_overrides,
                    "iterations": iterations,
                    "additional_context": additional_ctx,
                }
            ],
        }
        return payload

    def _validate(self) -> str | None:
        self._clear_log()
        payload = self._build_payload()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as tmp:
            json.dump(payload, tmp, indent=2, ensure_ascii=False)
            tmp_path = Path(tmp.name)
        try:
            load_experiment_config(tmp_path)
            self._log("[success] Config is valid.")
            return None
        except ExperimentConfigError as exc:
            self._log(f"[error] Validation failed: {exc}")
            return str(exc)
        except Exception as exc:
            self._log(f"[error] Unexpected validation error: {exc}")
            return str(exc)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _save_to_local(self) -> Path | None:
        self._clear_log()
        payload = self._build_payload()
        name = payload.get("experiment_name", "")
        safe = _safe_name(str(name))
        paths = get_project_paths()
        local_dir = paths.experiments_config / "local"
        local_dir.mkdir(parents=True, exist_ok=True)
        out_path = local_dir / f"{safe}.json"
        try:
            from orchestrator.shared.io.json_io import write_json

            write_json(out_path, payload)
        except OSError as exc:
            self._log(f"[error] Could not write config: {exc}")
            return None
        self._log(f"[success] Saved to: {out_path}")

        try:
            load_experiment_config(out_path)
            self._log("[success] Saved config passes validation.")
        except ExperimentConfigError as exc:
            self._log(f"[warning] Saved but validation failed: {exc}")
        return out_path

    def _save_and_run(self) -> None:
        saved = self._save_to_local()
        if saved is None:
            return

        active_runs = getattr(self.app, "active_runs_manager", None)
        if active_runs is not None:
            start_fn = getattr(active_runs, "start", None)
            if callable(start_fn):
                self._log("[info] Starting experiment via ActiveRunsManager...")
                run_id = start_fn(saved, dry_run=False)
                active_screen = self._try_import_active_run_screen()
                if active_screen is not None:
                    self.app.push_screen(active_screen(run_id))
                return

        self._log("[info] Config saved. Open 'Run Experiment' to launch it.")

    @staticmethod
    def _try_import_active_run_screen():
        try:
            from orchestrator.tui.screens.active_run_screen import ActiveRunScreen

            return ActiveRunScreen
        except ImportError:
            return None

    def _load_template(self) -> None:
        templates = self._templates
        if not templates:
            self._log("[warning] No templates found under configs/experiments/templates/")
            return
        if len(templates) == 1:
            self._load_config_from_path(templates[0])
            self._log(f"[info] Loaded template: {templates[0].name}")
            return
        self._log("[info] Multiple templates available. Picking first one. Use Load Local for more options.")
        self._load_config_from_path(templates[0])

    def _load_local(self) -> None:
        locals_ = self._local_configs
        if not locals_:
            self._log("[warning] No configs found under configs/experiments/local/")
            return
        if len(locals_) == 1:
            self._load_config_from_path(locals_[0])
            self._log(f"[info] Loaded local config: {locals_[0].name}")
            return
        self._log("[info] Multiple local configs available. Picking most recent one.")
        self._load_config_from_path(locals_[-1])

    def _load_config_from_path(self, path: Path) -> None:
        try:
            payload = read_json(path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            self._log(f"[error] Could not read {path.name}: {exc}")
            return
        if not isinstance(payload, dict):
            self._log(f"[error] {path.name} does not contain a JSON object.")
            return

        self._set_input("experiment_name", str(payload.get("experiment_name", "")))
        self._set_input("description", str(payload.get("description") or ""))
        sid = payload.get("solver_id")
        if isinstance(sid, str) and sid:
            try:
                self.query_one("#algorithm", Select).value = sid
            except Exception:
                pass
        self._set_input("target_file", str(payload.get("target_file", "")))
        self._set_input("baseline_run_dir", str(payload.get("baseline_run_dir", "")))

        cg = payload.get("candidate_generation")
        if isinstance(cg, dict):
            self._set_input("max_source_chars", str(cg.get("max_source_chars", "120000")))

        scope = payload.get("optimization_scope")
        if isinstance(scope, dict):
            af = scope.get("allowed_files")
            if isinstance(af, list):
                textarea = self.query_one("#allowed_files", TextArea)
                textarea.clear()
                textarea.insert("\n".join(str(f) for f in af))

        reporting = payload.get("reporting")
        if isinstance(reporting, dict):
            formats = reporting.get("formats")
            if isinstance(formats, list):
                self.query_one("#reporting_html", Switch).value = "html" in formats
                self.query_one("#reporting_pdf", Switch).value = "pdf" in formats
            renderer = reporting.get("renderer")
            if isinstance(renderer, str) and renderer in ("auto", "weasyprint", "playwright"):
                self.query_one("#reporting_renderer", Select).value = renderer
            if isinstance(reporting.get("fail_on_error"), bool):
                self.query_one("#reporting_fail_on_error", Switch).value = reporting["fail_on_error"]

        variants = payload.get("variants")
        if isinstance(variants, list) and variants:
            variant = variants[0]
            if isinstance(variant, dict):
                self._set_input("variant_id", str(variant.get("variant_id", "")))
                self._set_input("variant_description", str(variant.get("description") or ""))
                llm_cfg = variant.get("llm_config")
                if isinstance(llm_cfg, str):
                    self.query_one("#variant_llm_config", Select).value = llm_cfg
                self._set_input("iterations", str(variant.get("iterations", "3")))
                ac = variant.get("additional_context")
                if isinstance(ac, str) and ac:
                    textarea = self.query_one("#additional_context", TextArea)
                    textarea.clear()
                    textarea.insert(ac)
                overrides = variant.get("llm_overrides")
                if isinstance(overrides, dict):
                    if isinstance(overrides.get("provider"), str):
                        self.query_one("#llm_provider_override", Select).value = overrides["provider"]
                    if isinstance(overrides.get("model"), str):
                        self._set_input("llm_model_override", overrides["model"])
                    if isinstance(overrides.get("max_tokens"), int):
                        self._set_input("llm_max_tokens_override", str(overrides["max_tokens"]))
                    thinking = overrides.get("thinking")
                    if isinstance(thinking, dict):
                        if isinstance(thinking.get("enabled"), bool):
                            self.query_one("#thinking_enabled", Switch).value = thinking["enabled"]
                        if isinstance(thinking.get("effort"), str):
                            self.query_one("#thinking_effort", Select).value = thinking["effort"]

        self._log(f"[info] Loaded config from: {path}")

    def _set_input(self, widget_id: str, value: str) -> None:
        try:
            self.query_one(f"#{widget_id}", Input).value = value
        except Exception:
            pass
