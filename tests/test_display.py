from fjtop.config import DEFAULT_CONFIG, load_config
from fjtop.display import fmt_bytes, fmt_time


class TestFormatTime:
    def test_seconds(self):
        assert fmt_time(5) == "5s"

    def test_minutes(self):
        assert fmt_time(125) == "2m05s"

    def test_hours(self):
        assert fmt_time(3661) == "1h01m01s"

    def test_zero(self):
        assert fmt_time(0) == "0s"


class TestFormatBytes:
    def test_bytes(self):
        assert fmt_bytes(500) == "500.0B"

    def test_kilobytes(self):
        assert fmt_bytes(2048) == "2.0K"

    def test_megabytes(self):
        assert fmt_bytes(5 * 1024 * 1024) == "5.0M"

    def test_gigabytes(self):
        assert fmt_bytes(3 * 1024 * 1024 * 1024) == "3.0G"

    def test_negative(self):
        assert fmt_bytes(-1024) == "-1.0K"

    def test_zero(self):
        assert fmt_bytes(0) == "0.0B"


class TestDefaults:
    def test_config_has_display(self):
        assert "display" in DEFAULT_CONFIG

    def test_config_has_columns(self):
        assert "columns" in DEFAULT_CONFIG

    def test_default_refresh_rate(self):
        assert DEFAULT_CONFIG["display"]["refresh_rate"] == 1.0

    def test_default_sort(self):
        assert DEFAULT_CONFIG["display"]["sort_by"] == "cpu_pct"


class TestConfigLoad:
    def test_load_missing_file_returns_defaults(self):
        cfg = load_config("/nonexistent/fjtop/config.toml")
        assert cfg["display"]["refresh_rate"] == 1.0
