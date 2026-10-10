"""アクセスログを集計するパイプライン(同期版 gpframe によるドッグフーディング)。

    LogStats
    ├── Read        ファイルごとに Tail を持つ段。全部終われば lines を閉じる
    │   └── Tail:<file> × N
    ├── Parse       Parser を K 個持つ段。全部終われば records を閉じる
    │   └── Parser × K
    ├── Aggregate   records を集計し、ときどき結果を Shared に載せる
    └── Report      (追従するときだけ)一定の間隔で結果を表示する

段と段は容量に上限のある `Channel` でつなぎ、行はまとめて渡す。下流が遅ければ上流は
空きを待つので、メモリは入力の大きさによらない。上流の段が終わると出口の `Channel` を
閉じ、下流は残りを処理して終わる。どの段が失敗しても、ルートが全体を止める。

ログの 1 行の形式:

    2026-10-10T12:00:00 GET /index.html 200 12ms

    python examples/logstats.py access.log            # 読み終えたら結果を表示する
    python examples/logstats.py -f access.log         # 追従し、Ctrl-C で止める
"""

from __future__ import annotations

import argparse
import bisect
import re
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar, cast

import gpframe

LINE = re.compile(
    r"^(?P<time>\S+) (?P<method>[A-Z]+) (?P<path>\S+) (?P<status>\d{3}) (?P<ms>\d+)ms$"
)
BUCKETS = (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000)
T = TypeVar("T")


@dataclass(frozen=True)
class Entry:
    """Parse から Aggregate へ渡す 1 行分。"""


@dataclass(frozen=True)
class Record(Entry):
    method: str
    path: str
    status: int
    ms: int


@dataclass(frozen=True)
class Malformed(Entry):
    line: str


@dataclass(frozen=True)
class Stats:
    """集計の結果の写し。Aggregate が丸ごと差し替え、Report とルートが読む。"""

    total: int = 0
    malformed: int = 0
    by_status: tuple[tuple[int, int], ...] = ()
    histogram: tuple[int, ...] = (0,) * (len(BUCKETS) + 1)

    def percentile(self, q: float) -> str:
        if self.total == 0:
            return "-"
        rank = q * sum(self.histogram)
        seen = 0
        for bound, count in zip((*BUCKETS, None), self.histogram, strict=True):
            seen += count
            if seen >= rank:
                return f"<={bound}ms" if bound is not None else f">{BUCKETS[-1]}ms"
        return "-"

    def summary(self) -> str:
        statuses = " ".join(f"{s}:{n}" for s, n in self.by_status)
        return (
            f"total={self.total} malformed={self.malformed} {statuses} "
            f"p50{self.percentile(0.5)} p95{self.percentile(0.95)}"
        )


@dataclass(frozen=True)
class Config:
    paths: tuple[Path, ...]
    follow: bool = False
    parsers: int = 1
    batch: int = 500
    """まとめて渡す行の数。"""
    backlog: int = 20
    """段と段の間に溜めておけるまとまりの数。"""
    poll: float = 0.2
    """追従するとき、ファイルの新しい行を確かめる間隔の秒数。"""
    publish: float = 0.5
    """集計の結果を Shared に載せる間隔の秒数。"""
    report: float = 2.0
    stop_timeout: float = 5.0


# ---------------------------------------------------------------- 段


Worker = tuple[str, Callable[[gpframe.Context], object]]


def stage(
    ctx: gpframe.Context, workers: Sequence[Worker], output: gpframe.Channel[T]
) -> None:
    """ワーカーをまとめて動かす段。全部終われば(失敗でも停止でも)出口を閉じる。"""
    try:
        with ctx.session() as s:
            for name, routine in workers:
                _ = s.spawn(routine, name=name)
            for frame in s.wait_broken():
                frame.escalate()  # この段の失敗として上へ伝える
                s.stop()
    finally:
        output.close()


Batch = list  # 実行時の型。中身の型は変数の注釈で付ける


def tail(
    ctx: gpframe.Context,
    path: Path,
    lines: gpframe.Channel[list[str]],
    config: Config,
) -> None:
    """ファイルの行をまとめて lines に送る。追従するなら、停止まで新しい行を待ち続ける。"""
    with path.open(encoding="utf-8", errors="replace") as file:
        batch: list[str] = []
        pending = ""
        while not ctx.stopping:
            chunk = file.readline()
            if chunk.endswith("\n"):
                batch.append(pending + chunk[:-1])
                pending = ""
                if len(batch) >= config.batch:
                    if not lines.put(batch, ctx):  # 満杯なら空くまで待つ
                        return  # 停止か、下流が閉じた
                    batch = []
                continue
            if chunk:
                pending += chunk  # 書きかけの行。続きを待つ
                continue
            # いま読める行は読み終えた。溜まった分を送る。
            if batch:
                if not lines.put(batch, ctx):
                    return
                batch = []
            if not config.follow:
                if pending:
                    _ = lines.put([pending], ctx)
                return
            _ = ctx.wait_stop(config.poll)


def parse_line(line: str) -> Entry:
    match = LINE.match(line)
    if match is None:
        return Malformed(line)
    return Record(
        match["method"], match["path"], int(match["status"]), int(match["ms"])
    )


def parse(
    ctx: gpframe.Context,
    lines: gpframe.Channel[list[str]],
    entries: gpframe.Channel[list[Entry]],
) -> None:
    for batch in lines.receive(ctx):
        if not entries.put([parse_line(line) for line in batch], ctx):
            return


def aggregate(
    ctx: gpframe.Context,
    entries: gpframe.Channel[list[Entry]],
    stats: gpframe.Shared[Stats],
    config: Config,
) -> None:
    """集計は手元の可変な値で行い、ときどき不変の写しを Shared に載せる。"""
    total = 0
    by_status: Counter[int] = Counter()
    histogram = [0] * (len(BUCKETS) + 1)
    bad = 0

    def publish() -> None:
        stats.set(Stats(total, bad, tuple(sorted(by_status.items())), tuple(histogram)))

    last = time.monotonic()
    for batch in entries.receive(ctx):
        for entry in batch:
            if isinstance(entry, Record):
                total += 1
                by_status[entry.status] += 1
                histogram[bisect.bisect_left(BUCKETS, entry.ms)] += 1
            else:
                bad += 1
        now = time.monotonic()
        if now - last >= config.publish:
            publish()
            last = now
    publish()


def report(ctx: gpframe.Context, stats: gpframe.Shared[Stats], config: Config) -> None:
    while not ctx.wait_stop(config.report):
        print(stats.get().summary(), flush=True)


# ---------------------------------------------------------------- LogStats


def supervise(s: gpframe.Session) -> None:
    """直下のワーカーが一つでも失敗したら、それを上へ伝え、兄弟を止める。"""
    for frame in s.wait_broken():
        frame.escalate()
    s.stop()


class LogStats:
    """ワーカーの木の根。`stop()` はどのスレッドからでも、`run()` の前でも呼べる。"""

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.stats: gpframe.Shared[Stats] = gpframe.Shared(Stats, Stats())
        self._app: gpframe.Session = gpframe.session(timeout=config.stop_timeout)

    def run(self) -> Stats:
        config = self.config
        # 1 件ずつ渡すと受け渡しの費用が勝つので、行はまとめて渡す。
        # 上限を付けて、読む側が速くてもメモリが入力の大きさに比例して増えないようにする。
        lines: gpframe.Channel[list[str]] = gpframe.Channel(Batch, config.backlog)
        entries: gpframe.Channel[list[Entry]] = gpframe.Channel(Batch, config.backlog)
        readers: list[Worker] = [
            (f"Tail:{p.name}", lambda ctx, p=p: tail(ctx, p, lines, config))
            for p in config.paths
        ]
        parsers: list[Worker] = [
            (f"Parser{i}", lambda ctx: parse(ctx, lines, entries))
            for i in range(config.parsers)
        ]
        with self._app as app:
            _ = app.spawn(stage, readers, lines, name="Read")
            _ = app.spawn(stage, parsers, entries, name="Parse")
            _ = app.spawn(aggregate, entries, self.stats, config, name="Aggregate")
            if config.follow:
                _ = app.spawn(report, self.stats, config, name="Report")
            supervise(app)
        return self.stats.get()

    def stop(self) -> None:
        self._app.stop()


def describe(failed: gpframe.SessionFailed) -> str:
    lines: list[str] = []
    for frame in failed.frames:
        lines.append(f"{frame.name} failed: {frame.error!r}")
        report_ = frame.incomplete
        if report_ is not None:
            lines += [f"  {f.name}: {f.error!r}" for f in report_.broken]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="アクセスログを集計する")
    _ = parser.add_argument("paths", nargs="+", type=Path)
    _ = parser.add_argument("-f", "--follow", action="store_true")
    args = parser.parse_args(argv)
    config = Config(
        paths=tuple(cast("list[Path]", args.paths)),
        follow=cast("bool", args.follow),
    )
    try:
        stats = LogStats(config).run()
    except gpframe.SessionFailed as failed:
        print(describe(failed), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    print(stats.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
