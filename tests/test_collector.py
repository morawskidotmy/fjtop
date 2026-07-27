from fjtop.collector import Collector, _extract_name


class TestCollector:
    def test_has_firejail_when_installed(self):
        col = Collector()
        ok, msg = col.has_firejail()
        assert ok
        assert msg == ""

    def test_list_containers_returns_list(self):
        col = Collector()
        cs = col.list_containers()
        assert isinstance(cs, list)

    def test_collect_empty(self):
        col = Collector()
        result = col.collect([], 0.0)
        assert result == []


class TestExtractName:
    def test_firejail_firefox(self):
        assert _extract_name("firejail firefox") == "firefox"

    def test_firejail_binary_after_separator(self):
        cmd = "firejail --quiet --profile=/x/opencode.profile -- /home/dj/.opencode/bin/opencode"
        assert _extract_name(cmd) == "opencode"

    def test_firejail_with_options_no_separator(self):
        cmd = "firejail --quiet --profile=/x/mpv.profile /usr/bin/mpv"
        assert _extract_name(cmd) == "mpv"

    def test_plain_binary(self):
        assert _extract_name("/usr/bin/firefox") == "firefox"

    def test_unknown(self):
        assert _extract_name("") == "unknown"


class TestReadStat:
    def test_parses_stat_line_with_command_spaces(self):
        col = Collector()
        # Field numbers: 1 pid, 2 comm, 3 state, 4 ppid, 5 pgrp, 6 session,
        # 7 tty, 8 tpgid, 9 flags, 10 minflt, 11 cminflt, 12 majflt, 13 cmajflt,
        # 14 utime, 15 stime, 16 cutime, 17 cstime, 18 priority, 19 nice,
        # 20 num_threads, 21 itrealvalue, 22 starttime, 23 vsize, 24 rss, ...
        line = (
            "12345 (my app with spaces) S 1000 1000 1000 0 -1 "
            "4194560 10 20 30 40 50 60 70 80 90 100 110 120 130 140 150 160 170 180 190 200"
        )
        stat = col._parse_stat(line)
        assert stat is not None
        utime, stime, starttime = stat
        assert utime == 50
        assert stime == 60
        assert starttime == 130
