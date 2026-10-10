"""`Shared` の契約に対するテスト。"""

from __future__ import annotations

from typing import cast

import pytest
from shikumi_contrace import Phase, binds, upholds, violates

import gpframe
from contract.ports.surface import Shared
from contract.shared_contract import SharedContract


@binds[Shared[int]](gpframe.Shared)
class TestShared:
    @upholds(SharedContract.ValueAlwaysMatchesType)
    def test_construction_requires_matching_value(self) -> None:
        with Phase.MAIN:
            with pytest.raises(gpframe.DeclaredTypeError):
                _ = gpframe.Shared(int, cast("int", "zero"))
            with pytest.raises(gpframe.DeclaredTypeError):
                _ = gpframe.Shared(int, cast("int", None))
            cell = gpframe.Shared(int, 0)

        with Phase.VERIFY:
            assert cell.get() == 0

    @upholds(SharedContract.ValueAlwaysMatchesType)
    @upholds(SharedContract.set.ValueMatchesType)
    def test_set_replaces_value(self) -> None:
        with Phase.PREPARE:
            cell = gpframe.Shared(int, 0)

        with Phase.MAIN:
            cell.set(5)

        with Phase.VERIFY:
            assert cell.get() == 5

    @violates(SharedContract.set.ValueMatchesType)
    @upholds(SharedContract.ValueAlwaysMatchesType)
    def test_set_rejects_wrong_type_and_none(self) -> None:
        with Phase.PREPARE:
            cell = gpframe.Shared(int, 1)

        with Phase.MAIN:
            with pytest.raises(gpframe.DeclaredTypeError):
                cell.set(cast("int", "one"))
            with pytest.raises(gpframe.DeclaredTypeError):
                cell.set(cast("int", None))

        with Phase.VERIFY:
            assert cell.get() == 1

    @violates(SharedContract.apply.ResultMatchesType)
    @upholds(SharedContract.ValueAlwaysMatchesType)
    def test_apply_rejects_wrong_result_type(self) -> None:
        with Phase.PREPARE:
            cell = gpframe.Shared(int, 1)

        with Phase.MAIN, pytest.raises(gpframe.DeclaredTypeError):
            _ = cell.apply(lambda n: cast("int", str(n)))

        with Phase.VERIFY:
            assert cell.get() == 1

    @upholds(SharedContract.apply.ResultMatchesType)
    @upholds(SharedContract.apply.IsAtomic)
    def test_apply_does_not_lose_concurrent_updates(self) -> None:
        with Phase.PREPARE:
            counter = gpframe.Shared(int, 0)
            workers, rounds = 8, 2_000

            def increment(ctx: gpframe.Context, cell: gpframe.Shared[int]) -> None:
                for _ in range(rounds):
                    _ = cell.apply(lambda n: n + 1)

        with Phase.MAIN, gpframe.session(timeout=30) as s:
            for _ in range(workers):
                _ = s.spawn(increment, counter)

        with Phase.VERIFY:
            assert counter.get() == workers * rounds
