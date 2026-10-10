"""gpframe の開発用ウォッチャー(gpframe 自身によるドッグフーディング)。

ファイルの変更を検知して、文書の生成と検査を走らせ、生成した文書を HTTP で配信する。
gpframe の公開 API だけを使い、ワーカーの木として組み立てている。

    DevWatch
    ├── Watcher     監視対象のファイルの変更を検知する
    ├── Pipeline    変更ごとに、準備(文書の生成)と検査(並行)を走らせる
    │   └── (検査ごとのサブセッション) ruff-format / ruff / pyright / pytest ...
    └── Preview     生成した文書と、最後の結果(/status)を配信する

リポジトリのルートで実行する。

    python tools/devwatch.py              # 監視を始める。Ctrl-C で止める
    python tools/devwatch.py --once       # 一度だけ走らせ、結果を終了コードで返す
    python tools/devwatch.py --port 0     # 配信しない
"""

from __future__ import annotations

import argparse
import functools
import http.server
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import cast

import gpframe

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Step:
    """一つのコマンド。"""

    name: str
    argv: tuple[str, ...]


@dataclass(frozen=True)
class Config:
    root: Path
    watch: tuple[str, ...]
    """監視するファイルの glob パターン(`root` からの相対)。"""
    prepare: tuple[Step, ...]
    """検査の前に、順に走らせるコマンド。一つでも失敗すれば検査は走らせない。"""
    checks: tuple[Step, ...]
    """並行に走らせるコマンド。"""
    serve: Path | None = None
    """配信するディレクトリ。`None` なら配信しない。"""
    host: str = "127.0.0.1"
    port: int = 8765
    poll: float = 0.3
    """変更を確かめる間隔の秒数。"""
    settle: float = 0.3
    """最後の変更からこの秒数だけ静かになるまで、走らせるのを待つ。"""
    stop_timeout: float = 10.0


def default_config(root: Path = ROOT) -> Config:
    """このリポジトリ用の設定。"""
    python = sys.executable
    return Config(
        root=root,
        watch=(
            "src/**/*.py",
            "contract/**/*.py",
            "tests/**/*.py",
            "tools/**/*.py",
            "scripts/**/*.py",
            "devdocs/canonical_sources/**/*.py",
            "devdocs/config/*",
            "docs/**/*.md",
            "*.md",
            "pyproject.toml",
        ),
        prepare=(Step("render", (python, "scripts/render_devdocs.py")),),
        # 検査は CI と同じ tools/check.py で行う。配布物の検査(dist)は重いので CI に任せる。
        checks=tuple(
            Step(name, (python, "tools/check.py", name))
            for name in ("docs", "format", "lint", "types", "types-tests", "tests")
        ),
        serve=root / "devdocs" / "canonical_documents",
    )


# ---------------------------------------------------------------- 結果


class CommandError(Exception):
    """コマンドを起動できなかった。"""


@dataclass(frozen=True)
class StepResult:
    name: str
    returncode: int
    output: str
    seconds: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True)
class RunReport:
    number: int
    changed: tuple[str, ...]
    results: tuple[StepResult, ...]
    interrupted: bool = False

    @property
    def ok(self) -> bool:
        return not self.interrupted and all(r.ok for r in self.results)

    def _mark(self, result: StepResult) -> str:
        if result.ok:
            return "ok"
        # 停止で終わらせたコマンドは、失敗ではない。
        return "stopped" if self.interrupted and result.returncode < 0 else "FAIL"

    def summary(self) -> str:
        marks = " ".join(f"{r.name}:{self._mark(r)}" for r in self.results)
        state = "interrupted" if self.interrupted else ("ok" if self.ok else "FAILED")
        return f"#{self.number} {state} | {marks}"


@dataclass(frozen=True)
class Status:
    """Pipeline が書き、Preview が読む。丸ごと差し替える。"""

    running: int | None = None
    last: RunReport | None = None
    history: tuple[str, ...] = field(default=())


# ---------------------------------------------------------------- Watcher


def snapshot(root: Path, patterns: Iterable[str]) -> dict[str, int]:
    files: dict[str, int] = {}
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file() and "__pycache__" not in path.parts:
                try:
                    files[path.relative_to(root).as_posix()] = path.stat().st_mtime_ns
                except FileNotFoundError:
                    continue
    return files


def diff(before: Mapping[str, int], after: Mapping[str, int]) -> frozenset[str]:
    return frozenset(
        name
        for name in before.keys() | after.keys()
        if before.get(name) != after.get(name)
    )


def watcher(
    ctx: gpframe.Context, config: Config, changes: gpframe.Channel[frozenset[str]]
) -> None:
    """変更されたファイルの名前の集まりを `changes` に入れ続ける。"""
    before = snapshot(config.root, config.watch)
    while not ctx.wait_stop(config.poll):
        after = snapshot(config.root, config.watch)
        changed = diff(before, after)
        if changed:
            changes.put(changed)
        before = after


# ---------------------------------------------------------------- Pipeline


def run_step(ctx: gpframe.Context, config: Config, step: Step) -> StepResult:
    """コマンドを走らせる。停止が要求されたら、コマンドを終わらせる。"""
    started = time.monotonic()
    process = subprocess.Popen(
        step.argv,
        cwd=config.root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
    )
    stopping = ctx.on_stop(process.terminate)
    try:
        output, _ = process.communicate()
    finally:
        stopping.cancel()
    return StepResult(step.name, process.returncode, output, time.monotonic() - started)


def run_once(
    ctx: gpframe.Context, config: Config, number: int, changed: Iterable[str] = ()
) -> RunReport:
    """準備を順に、検査を並行に走らせる。"""
    results: list[StepResult] = []
    for step in config.prepare:
        result = run_step(ctx, config, step)
        results.append(result)
        if not result.ok:
            break
    else:
        with ctx.session(timeout=config.stop_timeout) as checks:
            frames = [
                checks.spawn(run_step, config, step, name=step.name)
                for step in config.checks
            ]
            # コマンドを起動できなかった(設定の誤り)なら、残りを止めて上へ伝える。
            # 失敗はすぐに知りたいので、起動した順に result() を待つ前に確かめる。
            for frame in checks.wait_broken():
                raise CommandError(frame.name) from frame.error
            # 停止の後に起動したものは stopped で、走っていないので結果がない。
            results.extend(frame.result() for frame in frames if not frame.stopped)
    return RunReport(number, tuple(sorted(changed)), tuple(results), ctx.stopping)


def report(run: RunReport) -> None:
    for result in run.results:
        if not result.ok and not run.interrupted:
            tail = "\n".join(result.output.rstrip().splitlines()[-30:])
            print(f"--- {result.name} (exit {result.returncode}) ---\n{tail}")
    print(run.summary(), flush=True)


def pipeline(
    ctx: gpframe.Context,
    config: Config,
    changes: gpframe.Channel[frozenset[str]],
    status: gpframe.Shared[Status],
) -> None:
    """起動時に一度、その後は変更が落ち着くたびに走らせる。"""
    number = 0
    changed: frozenset[str] = frozenset()
    while True:
        number += 1
        _ = status.apply(lambda s, n=number: replace(s, running=n))
        run = run_once(ctx, config, number, changed)
        _ = status.apply(
            lambda s, r=run: Status(None, r, (*s.history, r.summary())[-20:])
        )
        report(run)
        changed = collect(ctx, config, changes)
        if ctx.stopping:
            return


def collect(
    ctx: gpframe.Context,
    config: Config,
    changes: gpframe.Channel[frozenset[str]],
) -> frozenset[str]:
    """最初の変更を待ち、`settle` 秒静かになるまで続く変更をまとめる。停止なら空。"""
    first = changes.get(ctx)
    if first is None:
        return frozenset()
    pending = set(first)
    while (more := changes.get(ctx, timeout=config.settle)) is not None:
        pending |= more
    return frozenset() if ctx.stopping else frozenset(pending)


# ---------------------------------------------------------------- Preview


class PreviewHandler(http.server.SimpleHTTPRequestHandler):
    status: gpframe.Shared[Status] | None = None

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/status":
            self._send_status()
            return
        super().do_GET()

    def _send_status(self) -> None:
        current = self.status.get() if self.status is not None else Status()
        lines = [
            f"running: #{current.running}" if current.running else "idle",
            *reversed(current.history),
        ]
        last = current.last
        if last is not None:
            for result in last.results:
                if not result.ok:
                    lines += ["", f"--- {result.name} ---", result.output]
        body = "\n".join(lines).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        _ = self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def preview(
    ctx: gpframe.Context,
    config: Config,
    status: gpframe.Shared[Status],
    bound: queue.Queue[str],
) -> None:
    directory = config.serve if config.serve is not None else config.root
    handler = type("Handler", (PreviewHandler,), {"status": status})
    server = http.server.ThreadingHTTPServer(
        (config.host, config.port), functools.partial(handler, directory=str(directory))
    )
    with server:
        host, port = server.server_address[:2]
        bound.put(f"http://{host!s}:{port}/")
        _ = ctx.on_stop(server.shutdown)
        server.serve_forever()


# ---------------------------------------------------------------- DevWatch


def supervise(s: gpframe.Session) -> None:
    """直下のワーカーが一つでも失敗したら、それを上へ伝え、兄弟を止める。"""
    for frame in s.wait_broken():
        frame.escalate()
    s.stop()


class DevWatch:
    """ワーカーの木の根。`run()` を呼んだスレッドとは別のスレッドから `stop()` できる。"""

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.status: gpframe.Shared[Status] = gpframe.Shared(Status, Status())
        self.url: queue.Queue[str] = queue.Queue()
        self._app: gpframe.Session = gpframe.session(timeout=config.stop_timeout)

    def run(self) -> None:
        """止まるまで動く。ワーカーの失敗は `gpframe.SessionFailed` として送出する。"""
        # 型引数は実行時の検査に使えないので、変数の注釈で付ける。
        changes: gpframe.Channel[frozenset[str]] = gpframe.Channel(frozenset)
        with self._app as app:
            # stop() が先に呼ばれていれば、どれも stopped になって走らない。
            _ = app.spawn(watcher, self.config, changes, name="Watcher")
            _ = app.spawn(pipeline, self.config, changes, self.status, name="Pipeline")
            if self.config.serve is not None:
                _ = app.spawn(
                    preview, self.config, self.status, self.url, name="Preview"
                )
            supervise(app)

    def stop(self) -> None:
        self._app.stop()


def once(config: Config) -> RunReport:
    """一度だけ走らせる。"""
    with gpframe.session(timeout=config.stop_timeout) as app:
        frame = app.spawn(run_once, config, 1, name="Pipeline")
        supervise(app)
    return frame.result()


def describe(failed: gpframe.SessionFailed) -> str:
    lines: list[str] = []
    for frame in failed.frames:
        lines.append(f"{frame.name} failed: {frame.error!r}")
        incomplete = frame.incomplete
        if incomplete is not None:
            lines += [f"  {f.name}: {f.error!r}" for f in incomplete.broken]
            lines += [f"  {f.name}: did not stop" for f in incomplete.stuck]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="gpframe の開発用ウォッチャー")
    _ = parser.add_argument("--once", action="store_true", help="一度だけ走らせる")
    _ = parser.add_argument("--port", type=int, default=8765, help="0 なら配信しない")
    args = parser.parse_args(argv)
    port = cast("int", args.port)
    config = default_config()
    if port == 0:
        config = replace(config, serve=None)
    else:
        config = replace(config, port=port)
    try:
        if cast("bool", args.once):
            run = once(config)
            report(run)
            return 0 if run.ok else 1
        watch = DevWatch(config)
        threading.Thread(
            target=lambda: print(f"preview: {watch.url.get()}", flush=True), daemon=True
        ).start()
        watch.run()
    except gpframe.SessionFailed as failed:
        print(describe(failed), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("stopped", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
