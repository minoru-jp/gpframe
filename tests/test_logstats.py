"""ログ集計パイプライン(examples/logstats.py)のテスト。"""

from __future__ import annotations

import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

import gpframe
from examples import logstats

WAIT = 5.0


def write_log(path: Path, lines: list[str]) -> Path:
    _ = path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return path


def entry(status: int, ms: int, path: str = "/") -> str:
    return f"2026-10-10T12:00:00 GET {path} {status} {ms}ms"


def test_counts_every_file_and_malformed_line(tmp_path: Path) -> None:
    first = write_log(tmp_path / "a.log", [entry(200, 3), entry(404, 30), "noise"])
    second = write_log(tmp_path / "b.log", [entry(200, 700) for _ in range(1_200)])
    config = logstats.Config(paths=(first, second), batch=100)

    stats = logstats.LogStats(config).run()

    assert stats.total == 1_202
    assert stats.malformed == 1
    assert dict(stats.by_status) == {200: 1_201, 404: 1}
    assert stats.percentile(0.95) == "<=1000ms"


def test_a_missing_file_stops_the_pipeline(tmp_path: Path) -> None:
    good = write_log(tmp_path / "a.log", [entry(200, 1)])
    config = logstats.Config(paths=(good, tmp_path / "missing.log"))

    with pytest.raises(gpframe.SessionFailed) as caught:
        _ = logstats.LogStats(config).run()

    assert [f.name for f in caught.value.frames] == ["Read"]
    text = logstats.describe(caught.value)
    assert "Tail:missing.log: FileNotFoundError" in text


def test_follow_picks_up_new_lines_and_stops(tmp_path: Path) -> None:
    path = write_log(tmp_path / "live.log", [entry(200, 1)])
    config = logstats.Config(
        paths=(path,), follow=True, poll=0.02, publish=0.0, report=60.0
    )
    pipeline = logstats.LogStats(config)
    result: list[logstats.Stats] = []
    runner = threading.Thread(target=lambda: result.append(pipeline.run()))
    runner.start()

    def total() -> int:
        return pipeline.stats.get().total

    deadline = time.monotonic() + WAIT
    while total() < 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    with path.open("a", encoding="utf-8") as file:
        _ = file.write(entry(500, 2) + "\n" + "2026-10-10T12:00:01 GET / 2")  # 書きかけ
        file.flush()
        while total() < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        _ = file.write("00 9ms\n")  # 書きかけの行の続き
    while total() < 3 and time.monotonic() < deadline:
        time.sleep(0.01)

    began = time.monotonic()
    pipeline.stop()
    runner.join(WAIT)

    assert not runner.is_alive()
    assert time.monotonic() - began < WAIT
    assert result[0].total == 3
    assert dict(result[0].by_status) == {200: 2, 500: 1}


def test_stop_before_run(tmp_path: Path) -> None:
    path = write_log(tmp_path / "a.log", [entry(200, 1)])
    pipeline = logstats.LogStats(logstats.Config(paths=(path,)))
    pipeline.stop()
    assert pipeline.run().total == 0


def test_main_prints_the_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_log(tmp_path / "a.log", [entry(200, 1), entry(200, 1)])
    assert logstats.main([str(path)]) == 0
    assert capsys.readouterr().out.startswith("total=2 malformed=0 200:2")


def test_batches_keep_their_order(tmp_path: Path) -> None:
    lines = [entry(200 + n % 3, n) for n in range(1, 50)]
    path = write_log(tmp_path / "a.log", lines)
    config = replace(logstats.Config(paths=(path,)), batch=7)
    stats = logstats.LogStats(config).run()
    assert stats.total == 49
