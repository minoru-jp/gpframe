"""英語の公開文書(published document)が、日本語の canonical document と食い違っていないかを確かめる。

公開文書は canonical document を翻訳して作る(翻訳そのものは人か LLM が行う)。ここでは
翻訳が古くなっていないことと、翻訳で意味の要が崩れていないことを機械で確かめる。

- 対応: すべての canonical document に公開文書があり、余分な公開文書がない。
- 鮮度: 公開文書の先頭の印が、いまの canonical document の SHA-256 と一致する。
  canonical document が変われば、翻訳し直して印を付け直すまで失敗する。
- コード: Python のコード例が、コメントと docstring を除いて同じ構文木である。
- 規則: 仕様の規則の見出し(`## SESSION_001` など)が、同じ順に同じだけある。
- リンク: 相対リンクと、このリポジトリを指す GitHub のリンクの先が実在する。

    python scripts/published_docs.py check             # 確かめる
    python scripts/published_docs.py stamp README.md   # 翻訳し直した文書に印を付ける
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANONICAL = ROOT / "devdocs" / "canonical_documents"
REPOSITORY = "https://github.com/minoru-jp/gpframe/blob/main/"
TREE = "https://github.com/minoru-jp/gpframe/tree/main/"

# canonical document の置き場所(CANONICAL からの相対)と、公開文書の置き場所(ROOT からの相対)。
PLACES: tuple[tuple[str, str], ...] = (
    ("", ""),
    ("specification/", "docs/specification/"),
    ("specification_aio/", "docs/specification_aio/"),
)

STAMP = re.compile(
    r"\A<!-- Published from devdocs/canonical_documents/(?P<source>\S+) "
    r"sha256:(?P<digest>[0-9a-f]{64})\. .*? -->\n"
)
RULE = re.compile(r"^## ([A-Z]+_\d{3})\s*$", re.MULTILINE)
CODE = re.compile(r"^```python\n(.*?)^```", re.MULTILINE | re.DOTALL)
LINK = re.compile(r"\]\(([^)\s]+)\)")
CODE_FENCE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]*`")


@dataclass(frozen=True)
class Pair:
    canonical: Path
    published: Path

    @property
    def source_name(self) -> str:
        return self.canonical.relative_to(CANONICAL).as_posix()


def pairs() -> list[Pair]:
    found: list[Pair] = []
    for source_dir, published_dir in PLACES:
        for canonical in sorted((CANONICAL / source_dir).glob("*.md")):
            found.append(Pair(canonical, ROOT / published_dir / canonical.name))
    return found


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stamp_line(pair: Pair) -> str:
    return (
        f"<!-- Published from devdocs/canonical_documents/{pair.source_name} "
        f"sha256:{digest(pair.canonical)}. Translated from the Japanese canonical "
        "document; edit the canonical source instead of this file. -->\n"
    )


def code_shape(code: str) -> str:
    """コメントと docstring を除いた構文木。翻訳で変わってよいのはこの二つだけである。"""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(body, list)
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body[0] = ast.Pass()
    return ast.dump(tree, annotate_fields=False)


def check_pair(pair: Pair) -> list[str]:
    name = pair.published.relative_to(ROOT).as_posix()
    if not pair.published.exists():
        return [f"{name}: missing (published from {pair.source_name})"]
    text = pair.published.read_text(encoding="utf-8")
    source = pair.canonical.read_text(encoding="utf-8")
    problems: list[str] = []
    match = STAMP.match(text)
    if match is None or match["source"] != pair.source_name:
        problems.append(f"{name}: no valid stamp for {pair.source_name}")
    elif match["digest"] != digest(pair.canonical):
        problems.append(
            f"{name}: stale; {pair.source_name} changed. Re-translate it, then run "
            f"`python scripts/published_docs.py stamp {name}`"
        )
    if RULE.findall(text) != RULE.findall(source):
        problems.append(f"{name}: rule headings differ from {pair.source_name}")
    published_code = CODE.findall(text)
    source_code = CODE.findall(source)
    if len(published_code) != len(source_code):
        problems.append(
            f"{name}: {len(published_code)} code examples, expected {len(source_code)}"
        )
    else:
        for index, (ours, theirs) in enumerate(
            zip(published_code, source_code, strict=True)
        ):
            try:
                same = code_shape(ours) == code_shape(theirs)
            except SyntaxError as error:
                problems.append(
                    f"{name}: code example {index + 1} does not parse: {error}"
                )
                continue
            if not same:
                problems.append(
                    f"{name}: code example {index + 1} differs from the canonical one "
                    "beyond comments and docstrings"
                )
    problems += check_links(pair.published, text)
    return problems


def check_links(path: Path, text: str) -> list[str]:
    name = path.relative_to(ROOT).as_posix()
    problems: list[str] = []
    # コードの中の `[...](...)` はリンクではない。
    prose = INLINE_CODE.sub("", CODE_FENCE.sub("", text))
    for target in LINK.findall(prose):
        target = target.split("#", 1)[0]
        if not target:
            continue
        if target.startswith((REPOSITORY, TREE)):
            local = ROOT / target.removeprefix(REPOSITORY).removeprefix(TREE)
        elif "://" in target or target.startswith("mailto:"):
            continue
        else:
            local = path.parent / target
        if not local.exists():
            problems.append(f"{name}: broken link {target}")
    return problems


def extra_documents() -> list[str]:
    """canonical document に対応しない公開文書。"""
    expected = {p.published for p in pairs()}
    extra: list[str] = []
    for _, published_dir in PLACES[1:]:
        for path in sorted((ROOT / published_dir).glob("*.md")):
            if path not in expected:
                extra.append(
                    f"{path.relative_to(ROOT).as_posix()}: no canonical document"
                )
    return extra


def problems() -> list[str]:
    found: list[str] = []
    for pair in pairs():
        found += check_pair(pair)
    return found + extra_documents()


def stamp(names: list[str]) -> int:
    by_name = {p.published.relative_to(ROOT).as_posix(): p for p in pairs()}
    for name in names:
        pair = by_name.get(Path(name).as_posix())
        if pair is None:
            print(f"unknown published document: {name}", file=sys.stderr)
            return 2
        text = pair.published.read_text(encoding="utf-8")
        text = STAMP.sub("", text, count=1)
        _ = pair.published.write_text(stamp_line(pair) + text, encoding="utf-8")
        print(f"stamped {name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="英語の公開文書を確かめる。")
    commands = parser.add_subparsers(dest="command", required=True)
    _ = commands.add_parser("check", help="公開文書を確かめる")
    stamp_parser = commands.add_parser("stamp", help="翻訳し直した公開文書に印を付ける")
    _ = stamp_parser.add_argument("names", nargs="+")
    args = parser.parse_args(argv)
    if args.command == "stamp":
        return stamp(list(args.names))
    found = problems()
    for problem in found:
        print(problem)
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
