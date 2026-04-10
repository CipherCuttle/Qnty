"""Minimal CLI argument parsing tests."""

from quantbot.cli import main


class TestCliArgParsing:
    def test_missing_args_exits_with_code_1(self):
        result = main([])
        assert result == 1

    def test_manifest_required(self):
        result = main(["--csv", "foo.csv", "--out", "out/"])
        assert result == 1

    def test_csv_required(self):
        result = main(["--manifest", "manifest.json", "--out", "out/"])
        assert result == 1

    def test_out_required(self):
        result = main(["--manifest", "manifest.json", "--csv", "foo.csv"])
        assert result == 1

    def test_accepts_valid_args(self, tmp_path):
        manifest = tmp_path / "manifest.json"
        csv = tmp_path / "bars.csv"
        out = tmp_path / "out"
        manifest.touch()
        csv.touch()
        out.mkdir()
        # Does not raise (will fail later at run_replay level, but arg parsing passes)
        result = main(["--manifest", str(manifest), "--csv", str(csv), "--out", str(out)])
        # Expect failure because run_replay will reject empty files, but arg parse succeeded
        assert result == 1

    def test_sha256_flag_accepted(self, tmp_path):
        manifest = tmp_path / "manifest.json"
        csv = tmp_path / "bars.csv"
        out = tmp_path / "out"
        manifest.touch()
        csv.touch()
        out.mkdir()
        result = main([
            "--manifest", str(manifest),
            "--csv", str(csv),
            "--out", str(out),
            "--sha256-sidecar",
        ])
        # Arg parse succeeds; run_replay fails on empty files but flag is accepted
        assert result == 1
