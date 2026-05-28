"""Embedded config builder view."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Checkbox, Input, ListItem, ListView, RichLog, Select, Static, Switch, TextArea

from orchestrator.control import (
    ConfigBuilderSolverOption,
    discover_baseline_runs,
    discover_llm_configs,
    discover_local_configs,
    discover_template_configs,
    get_project_paths,
    list_config_builder_solver_options,
    safe_config_stem,
)
from orchestrator.experiments.experiment_config import (
    ExperimentConfigError,
    validate_experiment_config_dict,
)
from orchestrator.shared.io.json_io import read_json


DEFAULT_ADDITIONAL_CONTEXT = (
    "Optimize the selected solver implementation for runtime while preserving numerical "
    "behavior, solver API, output semantics, benchmark compatibility, and safety checks. "
    "Prefer one small, local, low-risk improvement per iteration. If no safe improvement "
    "is available, return a no-op candidate."
)


class ConfigFilePickerScreen(ModalScreen[Path | None]):
    """Simple modal file picker for config builder templates/local files."""

    DEFAULT_CSS = """
    ConfigFilePickerScreen {
        align: center middle;
    }
    #config-file-picker {
        width: 72;
        height: 22;
        background: #1f2937;
        border: solid #6b7280;
        padding: 1 2;
    }
    #config-file-picker Static {
        color: #f8fafc;
        margin-bottom: 1;
    }
    #config-file-list {
        height: 1fr;
        margin-bottom: 1;
        background: #374151;
    }
    #config-file-list ListItem {
        background: #374151;
        color: #f1f5f9;
    }
    #config-file-list ListItem > Static {
        background: #374151;
        color: #f1f5f9;
    }
    #config-file-list ListItem.-highlight {
        background: #2563eb;
        color: #ffffff;
    }
    #config-file-list ListItem.-highlight > Static {
        background: #2563eb;
        color: #ffffff;
    }
    """

    def __init__(self, title: str, paths: list[Path]) -> None:
        super().__init__()
        self._title = title
        self._paths = paths

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="config-file-picker"):
            yield Static(self._title)
            if self._paths:
                yield ListView(
                    *[ListItem(Static(str(path))) for path in self._paths],
                    id="config-file-list",
                )
            else:
                yield Static("No files found.")
            with Horizontal():
                yield Button("Load Selected", id="load-selected", variant="primary")
                yield Button("Cancel", id="cancel-picker")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-picker":
            self.dismiss(None)
            return
        if event.button.id == "load-selected":
            self._dismiss_selected()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "config-file-list":
            self._dismiss_selected()

    def _dismiss_selected(self) -> None:
        if not self._paths:
            self.dismiss(None)
            return
        try:
            index = self.query_one("#config-file-list", ListView).index
        except Exception:
            index = 0
        if index is None or index < 0 or index >= len(self._paths):
            index = 0
        self.dismiss(self._paths[index])


class ConfigBuilderView(Widget):
    """Form for creating flat single-variant experiment configs."""

    def __init__(self) -> None:
        super().__init__(id="view-config-builder")
        self._solver_options = list_config_builder_solver_options()
        self._llm_configs = discover_llm_configs()
        self._baseline_runs = discover_baseline_runs(self._default_solver_id())
        self._loading = False

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="config-builder-view"):
            yield Static("Build Experiment Config", classes="title")
            yield Static("Create one LLM optimization config and save it to configs/experiments/local/.", classes="subtitle")

            with VerticalScroll(id="builder-form"):
                yield Static("1. Basic", classes="title builder-section-title")
                yield Static("Experiment name", classes="field-label")
                yield Input(placeholder="experiment_name", id="experiment_name", classes="field-widget")
                yield Static("Description", classes="field-label")
                yield Input(placeholder="description (optional)", id="description", classes="field-widget")
                yield Static("Algorithm", classes="field-label")
                yield Select(self._algorithm_select_options(), value=self._default_solver_id() or "", id="algorithm", classes="field-widget")
                yield Static("Target file", classes="field-label")
                yield Static("Derived from the selected algorithm's solver manifest.", classes="subtitle helper-text")
                yield Input(placeholder="No target file found in solver manifest", id="target_file", classes="field-widget", disabled=True)
                yield Static("Baseline run", classes="field-label")
                yield Static("Baseline runs are filtered by selected algorithm.", classes="subtitle helper-text")
                yield Select(self._baseline_select_options(), id="baseline_run_sel", classes="field-widget")
                yield Static("Iterations", classes="field-label")
                yield Input(value="3", placeholder="iterations", id="iterations", classes="field-widget")

                yield Static("2. LLM", classes="title builder-section-title")
                yield Static("LLM config", classes="field-label")
                yield Select(self._llm_select_options(), id="llm_config", classes="field-widget")
                yield Static("Additional context", classes="field-label")
                yield TextArea(DEFAULT_ADDITIONAL_CONTEXT, id="additional_context", classes="field-widget")

                yield Static("3. Advanced", classes="title builder-section-title")
                yield Static("Reporting", classes="field-label")
                yield Static("HTML:", classes="field-label")
                yield Checkbox("", value=True, id="reporting_html", classes="field-widget")
                yield Static("PDF:", classes="field-label")
                yield Select(
                    [
                        ("disabled", "disabled"),
                        ("weasyprint: less accurate", "weasyprint"),
                        ("playwright: Chromium-based, more accurate", "playwright"),
                    ],
                    value="disabled",
                    id="reporting_pdf_renderer",
                    classes="field-widget",
                )

                yield Static("Selection parameters", classes="field-label")
                yield Static("gt_found_max_drop_points: optional maximum allowed drop in ground-truth pose found percentage. Empty means no extra drop limit.", classes="subtitle helper-text")
                yield Input(placeholder="empty = null, e.g. 0.5", id="gt_found_max_drop_points", classes="field-widget")

                yield Static("LLM overrides", classes="field-label")
                yield Input(placeholder="e.g. openai, anthropic, deepseek", id="llm_provider_override", classes="field-widget")
                yield Input(placeholder="e.g. gpt-4.1, claude-3-5-sonnet, deepseek-chat", id="llm_model_override", classes="field-widget")
                yield Input(placeholder="e.g. 4096", id="llm_max_tokens_override", classes="field-widget")
                yield Static("Thinking settings", classes="field-label")
                with Horizontal(id="thinking-enabled-row", classes="field-widget"):
                    yield Static("thinking.enabled:")
                    yield Switch(id="thinking_enabled", value=False)
                yield Select(
                    [("(no override)", ""), ("low", "low"), ("medium", "medium"), ("high", "high")],
                    value="",
                    id="thinking_effort",
                    classes="field-widget",
                )

            yield Static("Config summary", classes="title builder-section-title")
            yield Static("", id="config-builder-summary", classes="panel")
            yield RichLog(id="config-builder-status", classes="panel", wrap=True, highlight=True)

            with Horizontal(id="builder-buttons"):
                yield Button("Validate", id="btn-validate", classes="builder-button")
                yield Button("Save to local/", id="btn-save", classes="builder-button")
                yield Button("Clear Form", id="btn-clear", classes="builder-button")
            with Horizontal(id="builder-buttons-extra"):
                yield Button("Load Template", id="btn-load-template", classes="builder-button")
                yield Button("Load Local", id="btn-load-local", classes="builder-button")

    def on_mount(self) -> None:
        self._apply_solver_defaults(log=False)
        self._log("Config builder ready.")
        if not self._solver_options:
            self._log("[warning] No solver manifests found under cpp/bench/*/solvers/")
        if not self._llm_configs:
            self._log("[warning] No LLM configs found under configs/llm_*.json")
        self._update_summary()

    def refresh_view(self) -> None:
        """Refresh option sources without clearing user-entered form fields."""

        self._solver_options = list_config_builder_solver_options()
        self._llm_configs = discover_llm_configs()
        current_algorithm = self._select_value("algorithm") or self._default_solver_id() or ""
        try:
            algorithm = self.query_one("#algorithm", Select)
            options = self._algorithm_select_options()
            algorithm.set_options(options)
            values = {value for _label, value in options}
            algorithm.value = current_algorithm if current_algorithm in values else (self._default_solver_id() or "")
        except Exception:
            pass
        try:
            llm_select = self.query_one("#llm_config", Select)
            current_llm = self._select_value("llm_config")
            options = self._llm_select_options()
            llm_select.set_options(options)
            values = {value for _label, value in options}
            llm_select.value = current_llm if current_llm in values else ""
        except Exception:
            pass
        self._refresh_baseline_options(self._select_value("algorithm") or None)
        self._apply_solver_defaults(log=False)
        self._log("[info] Option lists refreshed.")
        self._update_summary()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "algorithm":
            self._apply_solver_defaults(log=True)
            return
        if event.select.id in {"baseline_run_sel", "llm_config", "reporting_pdf_renderer", "thinking_effort"}:
            self._update_summary()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id:
            self._update_summary()

    def on_switch_changed(self, _event: Switch.Changed) -> None:
        self._update_summary()

    def on_text_area_changed(self, _event: TextArea.Changed) -> None:
        self._update_summary()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "btn-validate":
            self._validate()
        elif btn_id == "btn-save":
            self._save_to_local()
        elif btn_id == "btn-clear":
            self._clear_form()
        elif btn_id == "btn-load-template":
            self._load_template()
        elif btn_id == "btn-load-local":
            self._load_local()

    def _default_solver_id(self) -> str | None:
        return self._solver_options[0].solver_id if self._solver_options else None

    def _algorithm_select_options(self) -> list[tuple[str, str]]:
        if not self._solver_options:
            return [("-- no algorithms found --", "")]
        return [(option.display_label, option.solver_id) for option in self._solver_options]

    def _llm_select_options(self) -> list[tuple[str, str]]:
        return [("-- select LLM config --", ""), *self._llm_configs]

    def _baseline_select_options(self) -> list[tuple[str, str]]:
        return self._baseline_runs[:]

    def _selected_solver_option(self) -> ConfigBuilderSolverOption | None:
        solver_id = self._select_value("algorithm")
        for option in self._solver_options:
            if option.solver_id == solver_id:
                return option
        return None

    def _apply_solver_defaults(self, *, log: bool) -> None:
        if self._loading:
            return
        option = self._selected_solver_option()
        target = option.default_target_file if option else None
        try:
            target_input = self.query_one("#target_file", Input)
            target_input.value = target or ""
            target_input.placeholder = "No target file found in solver manifest" if not target else ""
        except Exception:
            pass
        self._refresh_baseline_options(option.solver_id if option else None)
        if log:
            self._log("[info] Loaded defaults from solver manifest.")
        self._update_summary()

    def _refresh_baseline_options(self, solver_id: str | None) -> None:
        self._baseline_runs = discover_baseline_runs(solver_id)
        options = self._baseline_select_options()
        try:
            select = self.query_one("#baseline_run_sel", Select)
            old_value = select.value if isinstance(select.value, str) else ""
            select.set_options(options)
            values = {value for _label, value in options}
            select.value = old_value if old_value in values else (options[0][1] if options else "")
        except Exception:
            pass

    def _log(self, message: str) -> None:
        self.query_one("#config-builder-status", RichLog).write(message)

    def _clear_status(self) -> None:
        self.query_one("#config-builder-status", RichLog).clear()

    def _select_value(self, widget_id: str) -> str:
        try:
            value = self.query_one(f"#{widget_id}", Select).value
        except Exception:
            return ""
        return value if isinstance(value, str) else ""

    def _input_value(self, widget_id: str) -> str:
        return self.query_one(f"#{widget_id}", Input).value.strip()

    def _textarea_text(self, widget_id: str) -> str:
        return self.query_one(f"#{widget_id}", TextArea).text

    def _get_baseline_run_dir(self) -> str:
        return self._select_value("baseline_run_sel")

    def _parse_selection_gt_drop(self) -> float | None:
        raw = self._input_value("gt_found_max_drop_points")
        if not raw:
            return None
        try:
            value = float(raw)
        except ValueError as exc:
            raise ExperimentConfigError(
                "Field 'selection.gt_found_max_drop_points' must be empty or a non-negative number."
            ) from exc
        if not math.isfinite(value) or value < 0:
            raise ExperimentConfigError(
                "Field 'selection.gt_found_max_drop_points' must be empty or a finite non-negative number."
            )
        return value

    @staticmethod
    def _parse_optional_positive_int(raw: str, field_name: str) -> int | None:
        if not raw:
            return None
        try:
            value = int(raw)
        except (ValueError, TypeError) as exc:
            raise ExperimentConfigError(f"Field '{field_name}' must be empty or a positive integer.") from exc
        if str(value) != raw:
            raise ExperimentConfigError(f"Field '{field_name}' must be a positive integer (not a float).")
        if value <= 0:
            raise ExperimentConfigError(f"Field '{field_name}' must greater than 0.")
        return value

    def _build_payload(self) -> dict[str, Any]:
        html_enabled = bool(self.query_one("#reporting_html", Checkbox).value)
        pdf_renderer = self._select_value("reporting_pdf_renderer")
        pdf_enabled = pdf_renderer not in ("", "disabled")

        if html_enabled and pdf_enabled:
            formats = ["html", "pdf"]
            renderer = pdf_renderer
            reporting_enabled = True
        elif html_enabled:
            formats = ["html"]
            renderer = "auto"
            reporting_enabled = True
        elif pdf_enabled:
            formats = ["pdf"]
            renderer = pdf_renderer
            reporting_enabled = True
        else:
            formats = ["html"]
            renderer = "auto"
            reporting_enabled = False

        llm_overrides: dict[str, Any] = {}
        provider = self._input_value("llm_provider_override")
        model = self._input_value("llm_model_override")
        max_tokens_raw = self._input_value("llm_max_tokens_override")
        if provider:
            llm_overrides["provider"] = provider
        if model:
            llm_overrides["model"] = model
        if max_tokens_raw:
            llm_overrides["max_tokens"] = self._parse_optional_positive_int(max_tokens_raw, "llm_overrides.max_tokens")
        thinking: dict[str, Any] = {}
        if bool(self.query_one("#thinking_enabled", Switch).value):
            thinking["enabled"] = True
        effort = self._select_value("thinking_effort")
        if effort:
            thinking["effort"] = effort
        if thinking:
            llm_overrides["thinking"] = thinking

        iterations = self._parse_optional_positive_int(self._input_value("iterations"), "iterations")
        if iterations is None:
            raise ExperimentConfigError("Field 'iterations' is required and must be a positive integer.")

        return {
            "experiment_name": self._input_value("experiment_name"),
            "description": self._input_value("description") or None,
            "solver_id": self._select_value("algorithm") or None,
            "target_file": self._input_value("target_file"),
            "baseline_run_dir": self._get_baseline_run_dir(),
            "reporting": {
                "enabled": reporting_enabled,
                "formats": formats,
                "renderer": renderer,
            },
            "selection": {"gt_found_max_drop_points": self._parse_selection_gt_drop()},
            "llm_config": self._select_value("llm_config"),
            "llm_overrides": llm_overrides or None,
            "iterations": iterations,
            "additional_context": self._textarea_text("additional_context").strip() or None,
        }

    def _validate(self) -> str | None:
        self._clear_status()
        try:
            validate_experiment_config_dict(self._build_payload())
            self._log("[success] Config is valid.")
            return None
        except ExperimentConfigError as exc:
            self._log(f"[error] Validation failed: {exc}")
            return str(exc)
        except Exception as exc:
            self._log(f"[error] Unexpected validation error: {exc}")
            return str(exc)

    def _save_to_local(self) -> Path | None:
        self._clear_status()
        try:
            payload = self._build_payload()
            validate_experiment_config_dict(payload)
        except ExperimentConfigError as exc:
            self._log(f"[error] Validation failed: {exc}")
            return None
        project_paths = get_project_paths()
        local_dir = project_paths.experiments_config / "local"
        out_path = local_dir / f"{safe_config_stem(str(payload.get('experiment_name', '')))}.json"
        try:
            from orchestrator.shared.io.json_io import write_json

            write_json(out_path, payload)
        except OSError as exc:
            self._log(f"[error] Could not write config: {exc}")
            return None
        self._log(f"[success] Saved to: {out_path}")
        self._log("[success] Saved config passes validation.")
        self._update_summary()
        return out_path

    def _clear_form(self) -> None:
        self._set_input("experiment_name", "")
        self._set_input("description", "")
        self._set_select("algorithm", self._default_solver_id() or "")
        self._set_input("iterations", "3")
        self._set_select("llm_config", "")
        self._set_textarea("additional_context", DEFAULT_ADDITIONAL_CONTEXT)
        self.query_one("#reporting_html", Checkbox).value = True
        self._set_select("reporting_pdf_renderer", "disabled")
        self._set_input("gt_found_max_drop_points", "")
        self._set_input("llm_provider_override", "")
        self._set_input("llm_model_override", "")
        self._set_input("llm_max_tokens_override", "")
        self.query_one("#thinking_enabled", Switch).value = False
        self._set_select("thinking_effort", "")
        self._apply_solver_defaults(log=False)
        self._clear_status()
        self._log("[info] Form cleared.")
        self._update_summary()

    def _load_template(self) -> None:
        templates = discover_template_configs()
        if not templates:
            self._log("[warning] No templates found under configs/experiments/templates/")
            return
        self.app.push_screen(ConfigFilePickerScreen("Select a template config", templates), callback=self._on_config_file_selected)

    def _load_local(self) -> None:
        local_configs = discover_local_configs()
        if not local_configs:
            self._log("[warning] No configs found under configs/experiments/local/")
            return
        self.app.push_screen(ConfigFilePickerScreen("Select a local config", local_configs), callback=self._on_config_file_selected)

    def _on_config_file_selected(self, path: Path | None) -> None:
        if path is None:
            self._log("[info] File selection cancelled.")
            return
        self._load_config_from_path(path)

    def _load_config_from_path(self, path: Path) -> None:
        try:
            payload = read_json(path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            self._log(f"[error] Could not read {path.name}: {exc}")
            return
        if not isinstance(payload, dict):
            self._log(f"[error] {path.name} does not contain a JSON object.")
            return

        self._loading = True
        try:
            self._set_input("experiment_name", str(payload.get("experiment_name", "")))
            self._set_input("description", str(payload.get("description") or ""))
            solver_id = payload.get("solver_id")
            if isinstance(solver_id, str) and solver_id:
                self._set_select("algorithm", solver_id)
            self._set_input("target_file", str(payload.get("target_file", "")))
            reporting = payload.get("reporting")
            if isinstance(reporting, dict):
                fmt_list = reporting.get("formats")
                if isinstance(fmt_list, list):
                    self.query_one("#reporting_html", Checkbox).value = "html" in fmt_list
                    if "pdf" in fmt_list:
                        renderer = reporting.get("renderer")
                        self._set_select("reporting_pdf_renderer", renderer if isinstance(renderer, str) and renderer in ("weasyprint", "playwright") else "disabled")
                    else:
                        self._set_select("reporting_pdf_renderer", "disabled")
                elif reporting.get("enabled") is False:
                    self.query_one("#reporting_html", Checkbox).value = False
                    self._set_select("reporting_pdf_renderer", "disabled")
            selection = payload.get("selection")
            if isinstance(selection, dict):
                gt_drop = selection.get("gt_found_max_drop_points")
                self._set_input("gt_found_max_drop_points", "" if gt_drop is None else str(gt_drop))

            source = payload
            llm_cfg = source.get("llm_config")
            if isinstance(llm_cfg, str):
                self._set_select("llm_config", llm_cfg)
            self._set_input("iterations", str(source.get("iterations", "3")))
            ac = source.get("additional_context")
            if ac is None:
                self._set_textarea("additional_context", "")
            elif isinstance(ac, str):
                self._set_textarea("additional_context", ac)
            overrides = source.get("llm_overrides")
            self._apply_overrides(overrides if isinstance(overrides, dict) else None)
        finally:
            self._loading = False
        self._apply_solver_defaults(log=False)
        self._log(f"[info] Loaded config from: {path}")
        self._update_summary()

    def _apply_overrides(self, overrides: dict[str, Any] | None) -> None:
        self._set_input("llm_provider_override", "")
        self._set_input("llm_model_override", "")
        self._set_input("llm_max_tokens_override", "")
        self.query_one("#thinking_enabled", Switch).value = False
        self._set_select("thinking_effort", "")
        if overrides is None:
            return
        if isinstance(overrides.get("provider"), str):
            self._set_input("llm_provider_override", overrides["provider"])
        if isinstance(overrides.get("model"), str):
            self._set_input("llm_model_override", overrides["model"])
        if isinstance(overrides.get("max_tokens"), int):
            self._set_input("llm_max_tokens_override", str(overrides["max_tokens"]))
        thinking = overrides.get("thinking")
        if isinstance(thinking, dict):
            if isinstance(thinking.get("enabled"), bool):
                self.query_one("#thinking_enabled", Switch).value = thinking["enabled"]
            if isinstance(thinking.get("effort"), str):
                self._set_select("thinking_effort", thinking["effort"])

    def _set_input(self, widget_id: str, value: str) -> None:
        try:
            self.query_one(f"#{widget_id}", Input).value = value
        except Exception:
            pass

    def _set_select(self, widget_id: str, value: str) -> None:
        try:
            self.query_one(f"#{widget_id}", Select).value = value
        except Exception:
            pass

    def _set_textarea(self, widget_id: str, value: str) -> None:
        try:
            textarea = self.query_one(f"#{widget_id}", TextArea)
            textarea.clear()
            textarea.insert(value)
        except Exception:
            pass

    def _update_summary(self) -> None:
        try:
            payload = self._build_payload()
        except Exception:
            payload = {}
        name = payload.get("experiment_name") or "(not set)"
        solver = payload.get("solver_id") or "(not set)"
        target = payload.get("target_file") or "(no target from manifest)"
        baseline = payload.get("baseline_run_dir") or "(not set)"
        llm_config = payload.get("llm_config") or "(not set)"
        iterations = payload.get("iterations") or "(not set)"
        reporting = payload.get("reporting") if isinstance(payload.get("reporting"), dict) else {}
        formats = ", ".join(reporting.get("formats", [])) if isinstance(reporting, dict) else ""
        output = safe_config_stem(str(name)) if name != "(not set)" else "experiment_config"
        text = (
            f"Experiment name: {name}\n"
            f"Solver/algorithm: {solver}\n"
            f"Target file: {target}\n"
            f"Baseline run: {baseline}\n"
            f"LLM config: {llm_config}\n"
            f"Iterations: {iterations}\n"
            f"Reporting formats: {formats or 'none'}\n"
            f"Output path: configs/experiments/local/{output}.json"
        )
        try:
            self.query_one("#config-builder-summary", Static).update(text)
        except Exception:
            pass


__all__ = ["ConfigBuilderView", "ConfigFilePickerScreen", "DEFAULT_ADDITIONAL_CONTEXT"]
