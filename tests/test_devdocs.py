"""文書の正本に関するテスト。

- canonical document が正本から生成し直したものと一致していること
- README のコード例が実際に動き、書いてあるとおりの結果を出すこと
- 文書に注入するバージョンが pyproject.toml と一致していること
"""

from __future__ import annotations

import contextlib
import io
import json
import tomllib
from pathlib import Path

import pytest

from devdocs.canonical_sources.readme import canonical as readme
from scripts import render_devdocs

ROOT = Path(__file__).resolve().parent.parent


def test_canonical_documents_are_up_to_date() -> None:
    stale = render_devdocs.stale_documents()
    assert stale == [], "python scripts/render_devdocs.py で生成し直してください"


@pytest.mark.parametrize(
    ("example", "expected"),
    [
        (
            readme.TREE_EXAMPLE,
            "MessageWorker failed because Consumer: broker unreachable",
        ),
        (readme.QUICK_START, "3"),
        (readme.STOP_EXAMPLE, "True"),
        (readme.SHARED_EXAMPLE, "4000"),
        (readme.CHANNEL_EXAMPLE, "385"),
        (readme.COMPONENTS_EXAMPLE, "worker crashed"),
        (readme.AIO_EXAMPLE, "worker crashed"),
    ],
    ids=["tree", "quick start", "stop", "shared", "channel", "components", "aio"],
)
def test_readme_examples_run(example: str, expected: str) -> None:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(compile(example, "<README example>", "exec"), {"__name__": "__readme__"})  # noqa: S102 - README の例そのものを実行して確かめる
    assert output.getvalue().strip() == expected


def test_context_version_matches_project() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    context = json.loads(
        (ROOT / "devdocs" / "config" / "context.json").read_text(encoding="utf-8")
    )
    assert context["project"]["version"] == project["project"]["version"]
    assert (
        context["project"]["requires-python"] == project["project"]["requires-python"]
    )
