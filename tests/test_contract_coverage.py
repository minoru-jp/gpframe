"""契約と、テスト・仕様とのつながりの検査。

- 契約のすべての条項に、少なくとも一つのテストが結びついていること
- すべての条項が、根拠となる仕様の規則を `source` で指していること
- `source` が指す規則が、仕様書に実在すること
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from shikumi_contrace.reading import clauses_of, untested_clauses

from contract.aio_contract import (
    AsyncContextContract,
    AsyncFrameContract,
    AsyncSessionContract,
    AsyncStopHandleContract,
    LoopMonitorContract,
)
from contract.channel_contract import ChannelContract
from contract.session_contract import (
    ContextContract,
    FrameContract,
    SessionContract,
    StopHandleContract,
)
from contract.shared_contract import SharedContract
from tests import (
    test_aio_contract,
    test_aio_health_contract,
    test_channel_contract,
    test_lifetime_contract,
    test_session_contract,
    test_shared_contract,
    test_stop_contract,
)

CONTRACTS = (
    SessionContract,
    FrameContract,
    ContextContract,
    StopHandleContract,
    SharedContract,
    ChannelContract,
    AsyncSessionContract,
    AsyncFrameContract,
    AsyncContextContract,
    AsyncStopHandleContract,
    LoopMonitorContract,
)
TEST_MODULES = (
    test_session_contract,
    test_shared_contract,
    test_channel_contract,
    test_lifetime_contract,
    test_stop_contract,
    test_aio_contract,
    test_aio_health_contract,
)
DOCUMENTS = Path(__file__).resolve().parent.parent / "devdocs" / "canonical_documents"
SOURCE = re.compile(r"^(specification(?:_aio)?/[a-z_-]+\.md)#([A-Z]+_\d{3})$")


def _sources(contract: type) -> dict[str, list[str]]:
    return {
        clause.path: [
            a.text or "" for a in clause.annotations if a.word.name == "source"
        ]
        for clause in clauses_of(contract)
    }


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda c: c.__name__)
def test_every_clause_has_a_test(contract: type) -> None:
    missing = [clause.path for clause in untested_clauses(contract, TEST_MODULES)]
    assert missing == []


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda c: c.__name__)
def test_every_clause_cites_the_specification(contract: type) -> None:
    uncited = [path for path, sources in _sources(contract).items() if not sources]
    assert uncited == []


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda c: c.__name__)
def test_cited_rules_exist(contract: type) -> None:
    broken: list[str] = []
    for path, sources in _sources(contract).items():
        for text in sources:
            match = SOURCE.match(text)
            document = DOCUMENTS / match.group(1) if match else None
            if (
                match is None
                or document is None
                or not document.exists()
                or f"\n## {match.group(2)}\n"
                not in document.read_text(encoding="utf-8")
            ):
                broken.append(f"{path}: {text}")
    assert broken == []
