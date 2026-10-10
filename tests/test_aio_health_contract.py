"""ヘルスチェック(gpframe.aio.monitor)の契約に対するテスト。

ループを `time.sleep()` で実際にブロックして、停滞の検出と回復を確かめる。
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable, Coroutine
from typing import TypeVar

import pytest
from shikumi_contrace import Phase, binds, upholds

from contract.aio_contract import LoopMonitorContract
from contract.ports.aio_surface import LoopMonitor
from gpframe import aio

_MONITOR_SHAPE: Callable[..., LoopMonitor] = aio.LoopMonitor

T = TypeVar("T")
THRESHOLD = 0.1
INTERVAL = 0.02
BLOCK = 0.4


def run(scenario: Callable[[], Coroutine[object, object, T]]) -> T:
    return asyncio.run(scenario())


async def block_loop(seconds: float = BLOCK) -> None:
    """ループを実際にブロックする。前後で心拍を進めておく。"""
    await asyncio.sleep(INTERVAL * 3)
    time.sleep(seconds)  # noqa: ASYNC251 - 検出を確かめるため、わざとループをブロックする
    await asyncio.sleep(INTERVAL * 5)


@binds[LoopMonitor](aio.LoopMonitor)
class TestLoopMonitor:
    @upholds(LoopMonitorContract.ReportsEachStallOnce)
    @upholds(LoopMonitorContract.ReportsRecovery)
    def test_reports_stall_and_recovery_once(self) -> None:
        stalls: list[aio.LoopStall] = []
        recoveries: list[aio.LoopRecovery] = []

        async def scenario() -> None:
            async with aio.monitor(
                THRESHOLD,
                interval=INTERVAL,
                on_stall=stalls.append,
                on_recover=recoveries.append,
            ):
                await block_loop()

        with Phase.MAIN:
            run(scenario)

        with Phase.VERIFY:
            assert len(stalls) == 1
            assert len(recoveries) == 1
            assert stalls[0].lag > THRESHOLD
            assert stalls[0].stack is not None
            assert "block_loop" in "".join(stalls[0].stack)
            assert recoveries[0].duration >= BLOCK * 0.9

    @upholds(LoopMonitorContract.WarnsWithoutCallback)
    def test_warns_without_callback(self) -> None:
        async def scenario() -> None:
            async with aio.monitor(THRESHOLD, interval=INTERVAL):
                await block_loop()

        with Phase.MAIN, pytest.warns(aio.HealthWarning, match="stalled"):
            run(scenario)

    @upholds(LoopMonitorContract.CallbacksRunOnWatcherThread)
    def test_callbacks_run_on_the_watcher_thread(self) -> None:
        threads: list[int] = []

        async def scenario() -> int:
            async with aio.monitor(
                THRESHOLD,
                interval=INTERVAL,
                on_stall=lambda _: threads.append(threading.get_ident()),
                on_recover=lambda _: threads.append(threading.get_ident()),
            ):
                await block_loop()
            return threading.get_ident()

        with Phase.MAIN:
            loop_thread = run(scenario)

        with Phase.VERIFY:
            assert len(threads) == 2
            assert loop_thread not in threads

    @upholds(LoopMonitorContract.CallbackErrorsAreRecorded)
    def test_callback_errors_are_recorded_and_monitoring_continues(self) -> None:
        recoveries: list[aio.LoopRecovery] = []

        def bad_stall(_: aio.LoopStall) -> None:
            raise RuntimeError("logging failed")

        async def scenario() -> tuple[BaseException, ...]:
            async with aio.monitor(
                THRESHOLD,
                interval=INTERVAL,
                on_stall=bad_stall,
                on_recover=recoveries.append,
            ) as monitor:
                await block_loop()
            return monitor.errors

        with Phase.MAIN, pytest.warns(aio.HealthWarning, match="callback failed"):
            errors = run(scenario)

        with Phase.VERIFY:
            assert [type(e) for e in errors] == [RuntimeError]
            assert len(recoveries) == 1

    @upholds(LoopMonitorContract.NoCallbacksAfterClose)
    def test_no_callbacks_after_close(self) -> None:
        stalls: list[aio.LoopStall] = []

        async def scenario() -> None:
            async with aio.monitor(
                THRESHOLD, interval=INTERVAL, on_stall=stalls.append
            ):
                await asyncio.sleep(INTERVAL * 3)
            time.sleep(BLOCK)  # noqa: ASYNC251 - 閉じた後のブロックが報告されないことを確かめる
            await asyncio.sleep(INTERVAL * 3)

        with Phase.MAIN:
            run(scenario)

        with Phase.VERIFY:
            assert stalls == []

    @upholds(LoopMonitorContract.StateIsReadableFromAnyThread)
    def test_state_is_readable_from_another_thread(self) -> None:
        samples: list[tuple[bool, float]] = []

        async def scenario() -> tuple[bool, float]:
            async with aio.monitor(
                THRESHOLD, interval=INTERVAL, on_stall=lambda _: None
            ) as monitor:
                await asyncio.sleep(INTERVAL * 3)

                def sample() -> None:
                    time.sleep(BLOCK * 0.75)
                    samples.append((monitor.stalled, monitor.lag))

                sampler = threading.Thread(target=sample)
                sampler.start()
                time.sleep(BLOCK)  # noqa: ASYNC251 - 検出を確かめるため、わざとループをブロックする
                sampler.join()
                await asyncio.sleep(INTERVAL * 5)
                return monitor.stalled, monitor.lag

        with Phase.MAIN:
            after = run(scenario)

        with Phase.VERIFY:
            stalled, lag = samples[0]
            assert stalled is True
            assert lag > THRESHOLD
            assert after[0] is False
            assert after[1] < THRESHOLD
