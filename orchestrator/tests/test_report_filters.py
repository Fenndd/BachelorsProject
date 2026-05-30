from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from jinja2 import ChainableUndefined, Undefined
from markupsafe import Markup

from orchestrator.reporting.html_renderer import (
    _delta_pp,
    _diff_highlight,
    _display_value,
    _human_datetime,
    _human_duration,
    _human_int,
    _percent,
    _runtime_ns,
    _speedup,
    _yes_no,
)

_EM_DASH = "\u2014"


# ---------------------------------------------------------------------------
# display
# ---------------------------------------------------------------------------


def test_display_never_returns_not_available() -> None:
    values = [None, "", [], (), Undefined(), ChainableUndefined()]
    for v in values:
        result = _display_value(v)
        assert "Not available" not in result


def test_display_undefined_returns_dash() -> None:
    assert _display_value(Undefined()) == _EM_DASH
    assert _display_value(ChainableUndefined()) == _EM_DASH


def test_display_none_returns_dash() -> None:
    assert _display_value(None) == _EM_DASH


def test_display_empty_string_returns_dash() -> None:
    assert _display_value("") == _EM_DASH


def test_display_empty_list_returns_dash() -> None:
    assert _display_value([]) == _EM_DASH


def test_display_empty_tuple_returns_dash() -> None:
    assert _display_value(()) == _EM_DASH


def test_display_true_returns_yes() -> None:
    assert _display_value(True) == "Yes"


def test_display_false_returns_no() -> None:
    assert _display_value(False) == "No"


def test_display_float_compact_format() -> None:
    assert 0.1 <= float(_display_value(8.94764)) <= 10
    # 123456789.0 -> "1.23457e+08" with .6g
    assert _display_value(123456789.0) == "1.23457e+08"


def test_display_list_comma_separated() -> None:
    assert _display_value(["a", "b"]) == "a, b"


def test_display_dict_compact_json() -> None:
    result = _display_value({"key": "val"})
    assert "key" in result
    assert "val" in result


def test_display_plain_string_passthrough() -> None:
    assert _display_value("hello") == "hello"


def test_display_int_passthrough() -> None:
    assert _display_value(42) == "42"


# ---------------------------------------------------------------------------
# yes_no
# ---------------------------------------------------------------------------


def test_yes_no_true() -> None:
    assert _yes_no(True) == "Yes"


def test_yes_no_false() -> None:
    assert _yes_no(False) == "No"


def test_yes_no_none() -> None:
    assert _yes_no(None) == _EM_DASH


def test_yes_no_undefined() -> None:
    assert _yes_no(Undefined()) == _EM_DASH


# ---------------------------------------------------------------------------
# human_int
# ---------------------------------------------------------------------------


def test_human_int_with_thousands_separator() -> None:
    assert _human_int(670174) == "670\u202f174"


def test_human_int_small_number() -> None:
    assert _human_int(42) == "42"


def test_human_int_zero() -> None:
    assert _human_int(0) == "0"


def test_human_int_none() -> None:
    assert _human_int(None) == _EM_DASH


def test_human_int_undefined() -> None:
    assert _human_int(Undefined()) == _EM_DASH


def test_human_int_negative() -> None:
    assert _human_int(-1500) == "-1\u202f500"


# ---------------------------------------------------------------------------
# human_duration
# ---------------------------------------------------------------------------


def test_human_duration_hours_minutes_seconds() -> None:
    assert _human_duration(9182.08) == "2h 33m 02s"


def test_human_duration_minutes_seconds() -> None:
    assert _human_duration(65) == "1m 05s"


def test_human_duration_seconds_fractional() -> None:
    assert _human_duration(4.2) == "4.2s"


def test_human_duration_exactly_one_hour() -> None:
    assert _human_duration(3600) == "1h 00m 00s"


def test_human_duration_exactly_one_minute() -> None:
    assert _human_duration(60) == "1m 00s"


def test_human_duration_zero() -> None:
    assert _human_duration(0) == "0s"


def test_human_duration_none() -> None:
    assert _human_duration(None) == _EM_DASH


def test_human_duration_undefined() -> None:
    assert _human_duration(Undefined()) == _EM_DASH


# ---------------------------------------------------------------------------
# percent
# ---------------------------------------------------------------------------


def test_percent_formats_correctly() -> None:
    assert _percent(8.94764) == "8.95%"


def test_percent_zero() -> None:
    assert _percent(0) == "0.00%"


def test_percent_100() -> None:
    assert _percent(100) == "100.00%"


def test_percent_none() -> None:
    assert _percent(None) == _EM_DASH


def test_percent_undefined() -> None:
    assert _percent(Undefined()) == _EM_DASH


# ---------------------------------------------------------------------------
# speedup
# ---------------------------------------------------------------------------


def test_speedup_formats_correctly() -> None:
    assert _speedup(1.09827) == "1.098\u00d7"


def test_speedup_less_than_one() -> None:
    assert _speedup(0.9876) == "0.988\u00d7"


def test_speedup_none() -> None:
    assert _speedup(None) == _EM_DASH


def test_speedup_undefined() -> None:
    assert _speedup(Undefined()) == _EM_DASH


# ---------------------------------------------------------------------------
# human_datetime
# ---------------------------------------------------------------------------


def test_human_datetime_strips_microseconds_and_tz() -> None:
    result = _human_datetime("2026-05-26T07:38:17.382942+00:00")
    assert result == "2026-05-26 07:38"


def test_human_datetime_with_z_suffix() -> None:
    result = _human_datetime("2026-05-26T07:38:17Z")
    assert result == "2026-05-26 07:38"


def test_human_datetime_no_fractional_seconds() -> None:
    result = _human_datetime("2026-05-26T07:38:17+00:00")
    assert result == "2026-05-26 07:38"


def test_human_datetime_none() -> None:
    assert _human_datetime(None) == _EM_DASH


def test_human_datetime_undefined() -> None:
    assert _human_datetime(Undefined()) == _EM_DASH


def test_human_datetime_empty_string() -> None:
    assert _human_datetime("") == _EM_DASH


def test_human_datetime_parse_failure_fallback() -> None:
    result = _human_datetime("not-a-datetime")
    assert result == "not-a-datetime"


# ---------------------------------------------------------------------------
# diff_highlight
# ---------------------------------------------------------------------------


def test_diff_highlight_returns_markup() -> None:
    diff_text = (
        "--- a/file.cc\n"
        "+++ b/file.cc\n"
        "@@ -1,3 +1,4 @@\n"
        " unchanged\n"
        "-removed\n"
        "+added\n"
    )
    result = _diff_highlight(diff_text)
    assert isinstance(result, Markup)
    html_str = str(result)
    assert "added" in html_str
    assert "removed" in html_str


def test_diff_highlight_uses_self_contained_inline_styles() -> None:
    result = _diff_highlight("--- a/file\n+++ b/file\n@@ -1 +1 @@\n-old\n+new\n")
    html_str = str(result)

    assert "style=" in html_str
    assert "class=" not in html_str


def test_diff_highlight_escapes_raw_html() -> None:
    result = _diff_highlight("+<script>alert(1)</script>\n")
    html_str = str(result)

    assert "<script>" not in html_str
    assert "&lt;script&gt;" in html_str


def test_diff_highlight_unusual_text_does_not_crash() -> None:
    result = _diff_highlight("\x00\nnot really a diff\n@@\n")

    assert isinstance(result, Markup)
    assert "not really a diff" in str(result)


def test_diff_highlight_empty_returns_empty_markup() -> None:
    result = _diff_highlight("")
    assert isinstance(result, Markup)
    assert str(result) == ""


def test_diff_highlight_none_returns_empty_markup() -> None:
    result = _diff_highlight(None)
    assert isinstance(result, Markup)
    assert str(result) == ""


def test_diff_highlight_undefined_returns_dash() -> None:
    result = _diff_highlight(Undefined())
    assert isinstance(result, Markup)
    assert _EM_DASH in str(result)


def test_diff_highlight_without_pygments_safe_escapes(monkeypatch) -> None:
    """When Pygments is missing, output is escaped plain text."""

    import orchestrator.reporting.html_renderer as mod

    monkeypatch.setitem(__import__("sys").modules, "pygments", None)

    if "pygments" in __import__("sys").modules:
        monkeypatch.delitem(__import__("sys").modules, "pygments", raising=False)

    diff_text = "<script>alert(1)</script>\n+added line"
    result = mod._diff_highlight(diff_text)

    assert isinstance(result, Markup)
    html_str = str(result)
    assert "<script>" not in html_str or "&lt;script&gt;" in html_str


# ---------------------------------------------------------------------------
# runtime_ns
# ---------------------------------------------------------------------------


def test_runtime_ns_formats_two_decimals() -> None:
    assert _runtime_ns(485.988) == "485.99"


def test_runtime_ns_uses_thousands_separators() -> None:
    result = _runtime_ns(16193.123456)
    assert "\u202f" in result
    assert result == "16\u202f193.12"


def test_runtime_ns_none_returns_dash() -> None:
    assert _runtime_ns(None) == _EM_DASH


def test_runtime_ns_undefined_returns_dash() -> None:
    assert _runtime_ns(Undefined()) == _EM_DASH


def test_runtime_ns_integer_values() -> None:
    assert _runtime_ns(500) == "500.00"


def test_runtime_ns_zero() -> None:
    assert _runtime_ns(0) == "0.00"


# ---------------------------------------------------------------------------
# delta_pp
# ---------------------------------------------------------------------------


def test_delta_pp_formats_with_pp_suffix() -> None:
    result = _delta_pp(-1.25)
    assert result == "-1.25\u202fpp"


def test_delta_pp_formats_positive() -> None:
    result = _delta_pp(2.5)
    assert result == "2.50\u202fpp"


def test_delta_pp_formats_zero() -> None:
    result = _delta_pp(0.0)
    assert result == "0.00\u202fpp"


def test_delta_pp_none_returns_dash() -> None:
    assert _delta_pp(None) == _EM_DASH


def test_delta_pp_undefined_returns_dash() -> None:
    assert _delta_pp(Undefined()) == _EM_DASH
