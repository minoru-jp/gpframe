"""開発用ウォッチャー(tools/devwatch.py)のテスト。

本物の検査の代わりに、すぐ終わる python のコマンドを使う。
"""

from __future__ import annotations

import sys
import time
import urllib.request
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

import gpframe
from tools import devwatch

WAIT = 10.0


def command(name: str, code: str) -> devwatch.Step:
    return devwatch.Step(name, (sys.executable, "-c", code))


OK = "print('fine')"
FAIL = "import sys; print('bad'); sys.exit(3)"
SLOW = "import time; time.sleep(30)"
# 停止(SIGTERM)を受けると、成功として終わる。
GRACEFUL = (
    "import signal, sys, time; "
    "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); time.sleep(30)"
)


def make_config(root: Path, *checks: devwatch.Step) -> devwatch.Config:
    (root / "src").mkdir()
    _ = (root / "src" / "a.py").write_text("x = 1\n")
    return devwatch.Config(
        root=root,
        watch=("src/**/*.py",),
        prepare=(command("render", OK),),
        checks=checks or (command("lint", OK),),
        serve=None,
        poll=0.05,
        settle=0.1,
        stop_timeout=5.0,
    )


def until(predicate: Callable[[], bool], timeout: float = WAIT) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            pytest.fail("condition was not met in time")
        time.sleep(0.02)


@pytest.fixture
def background() -> Iterator[Callable[[devwatch.DevWatch], Future[None]]]:
    with ThreadPoolExecutor(max_workers=1) as pool:
        yield lambda watch: pool.submit(watch.run)


class TestOnce:
    def test_reports_each_step(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, command("lint", OK), command("tests", FAIL))
        run = devwatch.once(config)
        assert [(r.name, r.returncode) for r in run.results] == [
            ("render", 0),
            ("lint", 0),
            ("tests", 3),
        ]
        assert run.ok is False
        assert "tests:FAIL" in run.summary()

    def test_failed_preparation_skips_the_checks(self, tmp_path: Path) -> None:
        config = replace(make_config(tmp_path), prepare=(command("render", FAIL),))
        run = devwatch.once(config)
        assert [r.name for r in run.results] == ["render"]

    def test_a_command_that_cannot_start_fails_the_session(
        self, tmp_path: Path
    ) -> None:
        missing = devwatch.Step("ghost", (str(tmp_path / "no-such-command"),))
        config = make_config(tmp_path, command("lint", SLOW), missing)
        started = time.monotonic()
        with pytest.raises(gpframe.SessionFailed) as caught:
            _ = devwatch.once(config)
        # 兄弟の検査は止められ、30 秒待たずに終わる。
        assert time.monotonic() - started < WAIT
        text = devwatch.describe(caught.value)
        assert "Pipeline failed: CommandError('ghost')" in text
        assert "ghost: FileNotFoundError" in text


class TestWatch:
    def test_runs_again_after_a_change(
        self,
        tmp_path: Path,
        background: Callable[[devwatch.DevWatch], Future[None]],
    ) -> None:
        watch = devwatch.DevWatch(make_config(tmp_path))
        running = background(watch)

        def last_number() -> int:
            last = watch.status.get().last
            return 0 if last is None else last.number

        until(lambda: last_number() == 1)
        _ = (tmp_path / "src" / "b.py").write_text("y = 2\n")
        until(lambda: last_number() == 2)
        last = watch.status.get().last
        assert last is not None
        assert last.changed == ("src/b.py",)
        watch.stop()
        running.result(WAIT)

    def test_stop_ends_a_running_command(
        self,
        tmp_path: Path,
        background: Callable[[devwatch.DevWatch], Future[None]],
    ) -> None:
        watch = devwatch.DevWatch(make_config(tmp_path, command("tests", SLOW)))
        running = background(watch)
        until(lambda: watch.status.get().running == 1)
        time.sleep(0.2)
        started = time.monotonic()
        watch.stop()
        running.result(WAIT)
        assert time.monotonic() - started < WAIT
        last = watch.status.get().last
        assert last is not None
        assert last.interrupted
        assert "tests:stopped" in last.summary()

    def test_stop_after_a_graceful_preparation(
        self,
        tmp_path: Path,
        background: Callable[[devwatch.DevWatch], Future[None]],
    ) -> None:
        # 準備が停止を受けて成功で終わると、停止したサブセッションで検査を起動しようとする。
        config = replace(make_config(tmp_path), prepare=(command("render", GRACEFUL),))
        watch = devwatch.DevWatch(config)
        running = background(watch)
        until(lambda: watch.status.get().running == 1)
        time.sleep(0.2)
        watch.stop()
        running.result(WAIT)
        last = watch.status.get().last
        assert last is not None
        assert [r.name for r in last.results] == ["render"]

    def test_stop_before_run(self, tmp_path: Path) -> None:
        watch = devwatch.DevWatch(make_config(tmp_path))
        watch.stop()
        watch.run()
        assert watch.status.get().last is None

    def test_preview_serves_files_and_status(
        self,
        tmp_path: Path,
        background: Callable[[devwatch.DevWatch], Future[None]],
    ) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        _ = (docs / "index.md").write_text("# hello\n")
        config = replace(make_config(tmp_path), serve=docs, port=0)
        watch = devwatch.DevWatch(config)
        running = background(watch)
        url = watch.url.get(timeout=WAIT)
        until(lambda: watch.status.get().last is not None)
        with urllib.request.urlopen(url + "index.md", timeout=WAIT) as page:
            assert page.read() == b"# hello\n"
        with urllib.request.urlopen(url + "status", timeout=WAIT) as page:
            assert b"#1 ok" in page.read()
        watch.stop()
        running.result(WAIT)

    def test_a_port_in_use_fails_the_session(self, tmp_path: Path) -> None:
        config = replace(make_config(tmp_path), serve=tmp_path, port=0)
        first = devwatch.DevWatch(config)
        with ThreadPoolExecutor(max_workers=1) as pool:
            running = pool.submit(first.run)
            port = int(first.url.get(timeout=WAIT).rsplit(":", 1)[1].strip("/"))
            second = devwatch.DevWatch(replace(config, port=port))
            with pytest.raises(gpframe.SessionFailed) as caught:
                second.run()
            first.stop()
            running.result(WAIT)
        assert [f.name for f in caught.value.frames] == ["Preview"]
        assert isinstance(caught.value.exceptions[0], OSError)


def test_diff_finds_added_removed_and_changed() -> None:
    before = {"a": 1, "b": 1, "c": 1}
    after = {"a": 1, "b": 2, "d": 1}
    assert devwatch.diff(before, after) == {"b", "c", "d"}
