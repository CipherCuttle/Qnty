"""Smoke tests for determinism helpers.

These tests verify that canonical_json_dumps produces consistent output
and that sha256_file returns the same hash for identical files.
"""

import json
import tempfile
from pathlib import Path

from quantbot.core.determinism import canonical_json_dumps, sha256_file


class TestCanonicalJsonDumps:
    """Tests for canonical_json_dumps."""

    def test_sorted_keys(self):
        """Dict with same values in different key order produces same output."""
        a = {"z": 1, "a": 2, "m": 3}
        b = {"a": 2, "m": 3, "z": 1}
        assert canonical_json_dumps(a) == canonical_json_dumps(b)

    def test_no_extra_whitespace(self):
        """Output contains no extra whitespace."""
        obj = {"a": 1, "b": 2}
        result = canonical_json_dumps(obj)
        assert " " not in result

    def test_deterministic_list_order(self):
        """Lists maintain order and are part of canonical output."""
        a = [3, 1, 4, 1, 5]
        b = [3, 1, 4, 1, 5]
        assert canonical_json_dumps(a) == canonical_json_dumps(b)


class TestSha256File:
    """Tests for sha256_file."""

    def test_same_content_same_hash(self, tmp_path):
        """Identical files produce the same hash."""
        file_a = tmp_path / "a.txt"
        file_b = tmp_path / "b.txt"
        file_a.write_bytes(b"hello world")
        file_b.write_bytes(b"hello world")
        assert sha256_file(file_a) == sha256_file(file_b)

    def test_different_content_different_hash(self, tmp_path):
        """Different files produce different hashes."""
        file_a = tmp_path / "a.txt"
        file_b = tmp_path / "b.txt"
        file_a.write_bytes(b"hello")
        file_b.write_bytes(b"world")
        assert sha256_file(file_a) != sha256_file(file_b)

    def test_empty_file_hash(self, tmp_path):
        """Empty file has a known SHA-256 hash."""
        file = tmp_path / "empty.txt"
        file.write_bytes(b"")
        # SHA-256 of empty string
        assert sha256_file(file) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
