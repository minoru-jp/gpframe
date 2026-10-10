"""テスト共通の部品。"""

from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest

import gpframe


@pytest.fixture
def gate() -> Iterator[threading.Event]:
    """フレームを止めておくための門。テストの終わりに必ず開ける。

    停止要求を無視するフレーム(stuck frame)を作るのに使う。
    """
    event = threading.Event()
    yield event
    event.set()


def succeed(ctx: gpframe.Context, value: int = 1) -> int:
    return value


def fail(ctx: gpframe.Context, message: str = "boom") -> int:
    raise ValueError(message)


def until_stopped(ctx: gpframe.Context) -> str:
    """停止が要求されるまで動き続ける、行儀のよいルーティン。"""
    while not ctx.stopping:
        _ = ctx.wait_stop(0.01)
    return "stopped"


def blocked(ctx: gpframe.Context, gate: threading.Event) -> str:
    """停止要求を無視して門が開くのを待つ、止まらないルーティン。"""
    _ = gate.wait()
    return "released"
