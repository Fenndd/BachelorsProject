from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

import json
from pathlib import Path

import pytest

from orchestrator.shared.io.json_io import read_json, read_json_object, write_json


class TestReadJson:
    def test_plain_json_object(self, tmp_path: Path) -> None:
        path = tmp_path / "data.json"
        path.write_text('{"key": "value"}\n', encoding="utf-8")
        result = read_json(path)
        assert result == {"key": "value"}

    def test_utf8_bom_json(self, tmp_path: Path) -> None:
        path = tmp_path / "bom.json"
        path.write_bytes(b'\xef\xbb\xbf{"k": 1}\n')
        result = read_json(path)
        assert result == {"k": 1}

    def test_json_decode_error_propagates(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8-sig")
        with pytest.raises(json.JSONDecodeError):
            read_json(path)

    def test_missing_file_propagates_os_error(self, tmp_path: Path) -> None:
        with pytest.raises(OSError):
            read_json(tmp_path / "nonexistent.json")


class TestReadJsonObject:
    def test_valid_dict(self, tmp_path: Path) -> None:
        path = tmp_path / "obj.json"
        path.write_text('{"a": 1}\n', encoding="utf-8")
        result = read_json_object(path)
        assert result == {"a": 1}

    def test_bom_dict(self, tmp_path: Path) -> None:
        path = tmp_path / "bom_obj.json"
        path.write_bytes(b'\xef\xbb\xbf{"x": true}\n')
        result = read_json_object(path)
        assert result == {"x": True}

    def test_list_raises_value_error(self, tmp_path: Path) -> None:
        path = tmp_path / "list.json"
        path.write_text("[1, 2, 3]\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Expected a JSON object"):
            read_json_object(path)

    def test_string_raises_value_error(self, tmp_path: Path) -> None:
        path = tmp_path / "string.json"
        path.write_text('"hello"\n', encoding="utf-8")
        with pytest.raises(ValueError, match="Expected a JSON object"):
            read_json_object(path)

    def test_number_raises_value_error(self, tmp_path: Path) -> None:
        path = tmp_path / "num.json"
        path.write_text("42\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Expected a JSON object"):
            read_json_object(path)


class TestWriteJson:
    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "out.json"
        result = write_json(path, {"hello": "world"})
        assert result == path
        assert path.is_file()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload == {"hello": "world"}

    def test_writes_utf8(self, tmp_path: Path) -> None:
        path = tmp_path / "utf8.json"
        write_json(path, {"greeting": "cau"})
        text = path.read_text(encoding="utf-8")
        assert "cau" in text
        # No BOM in output
        raw = path.read_bytes()
        assert raw[:3] != b"\xef\xbb\xbf"

    def test_compact_mode(self, tmp_path: Path) -> None:
        path = tmp_path / "compact.json"
        write_json(path, {"a": 1, "b": 2}, compact=True)
        text = path.read_text(encoding="utf-8")
        assert "\n" not in text.strip("\n")
