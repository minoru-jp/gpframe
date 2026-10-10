"""gpframe のすべての検査をまとめて走らせる。CI、リリース、開発用ウォッチャーが同じものを使う。

リポジトリのルートで実行する。

    python tools/check.py                  # すべての検査
    python tools/check.py lint tests       # 選んだ検査だけ
    python tools/check.py dist --tag v0.1.0 --dist-dir dist
                                           # 配布物を作って確かめ、dist/ に残す(リリース用)

検査:

    docs         canonical document が正本から生成し直したものと同じで、英語の公開文書が
                 canonical document と食い違っていない
    format       ruff format --check
    lint         ruff check
    types        basedpyright(src、contract/ports、tools、examples)
    types-tests  basedpyright -p tests(テスト、契約、文書の正本を利用側として)
    tests        pytest(契約の検査を含む)
    dist         sdist と wheel を作り、twine check、中身の検査、きれいな venv での動作確認

失敗した検査があっても残りを続け、最後にまとめて報告する。一つでも失敗すれば終了コードは 1。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import venv
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class Options:
    tag: str | None = None
    dist_dir: str | None = None


@dataclass(frozen=True)
class Outcome:
    ok: bool
    output: str


def command(*argv: str) -> Callable[[Options], Outcome]:
    def run(_: Options) -> Outcome:
        done = subprocess.run(
            argv, cwd=ROOT, capture_output=True, text=True, check=False
        )
        return Outcome(done.returncode == 0, done.stdout + done.stderr)

    return run


# ---------------------------------------------------------------- docs


def check_docs(_: Options) -> Outcome:
    # ROOT を sys.path に入れた後で読む。
    from scripts import published_docs, render_devdocs

    lines: list[str] = []
    stale = render_devdocs.stale_documents()
    lines += [
        f"stale canonical document: {name} (run: python scripts/render_devdocs.py)"
        for name in stale
    ]
    lines += published_docs.problems()
    return Outcome(not lines, "\n".join(lines))


# ---------------------------------------------------------------- dist


REQUIRED_IN_WHEEL = (
    "gpframe/__init__.py",
    "gpframe/py.typed",
    "gpframe/_channel.py",
    "gpframe/_errors.py",
    "gpframe/_session.py",
    "gpframe/_shared.py",
    "gpframe/aio/__init__.py",
    "gpframe/aio/_monitor.py",
    "gpframe/aio/_session.py",
)
REQUIRED_IN_SDIST = (
    "PKG-INFO",
    "pyproject.toml",
    "README.md",
    "LICENSE",
    *(f"src/{name}" for name in REQUIRED_IN_WHEEL),
)

SMOKE = """
import asyncio, gpframe
from gpframe import aio

def double(ctx, n):
    return n * 2

with gpframe.session(timeout=5) as s:
    frames = [s.spawn(double, n) for n in range(3)]
    for frame in s.wait_broken():
        frame.escalate()
assert [f.result() for f in frames] == [0, 2, 4]

async def triple(ctx, n):
    return n * 3

async def main():
    async with aio.session(timeout=5) as s:
        frame = s.spawn(triple, 2)
    return await frame.result()

assert asyncio.run(main()) == 6
print(gpframe.__name__, "ok")
"""


def project() -> dict[str, object]:
    with (ROOT / "pyproject.toml").open("rb") as file:
        data = tomllib.load(file)
    return cast("dict[str, object]", data["project"])


def check_dist(args: Options) -> Outcome:
    version = str(project()["version"])
    lines: list[str] = []
    tag = args.tag
    if tag is not None and tag != f"v{version}":
        lines.append(f"tag {tag!r} does not match the project version v{version}")
    changelog = (
        ROOT / "devdocs" / "canonical_sources" / "changelog" / "canonical.py"
    ).read_text(encoding="utf-8")
    if f'version @= "{version}"' not in changelog:
        lines.append(f"the CHANGELOG has no entry for {version}")
    context = cast(
        "dict[str, dict[str, str]]",
        json.loads(
            (ROOT / "devdocs" / "config" / "context.json").read_text(encoding="utf-8")
        ),
    )
    if context["project"]["version"] != version:
        lines.append("devdocs/config/context.json has a different version")

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "dist"
        built = subprocess.run(
            [
                PYTHON,
                "-m",
                "build",
                "--sdist",
                "--wheel",
                "--outdir",
                str(out),
                str(ROOT),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if built.returncode != 0:
            return Outcome(False, "\n".join([*lines, built.stdout, built.stderr]))
        wheels = sorted(out.glob("*.whl"))
        sdists = sorted(out.glob("*.tar.gz"))
        if [w.name for w in wheels] != [f"gpframe-{version}-py3-none-any.whl"]:
            lines.append(f"unexpected wheels: {[w.name for w in wheels]}")
        if [s.name for s in sdists] != [f"gpframe-{version}.tar.gz"]:
            lines.append(f"unexpected sdists: {[s.name for s in sdists]}")
        twine = subprocess.run(
            [PYTHON, "-m", "twine", "check", "--strict", *map(str, out.iterdir())],
            capture_output=True,
            text=True,
            check=False,
        )
        if twine.returncode != 0:
            lines.append("twine check failed:\n" + twine.stdout + twine.stderr)
        if wheels:
            lines += inspect_wheel(wheels[0], version)
            lines += smoke_test(wheels[0], Path(tmp))
        if sdists:
            lines += inspect_sdist(sdists[0], version)
        keep = args.dist_dir
        if keep is not None and not lines:
            target = ROOT / keep
            target.mkdir(parents=True, exist_ok=True)
            for path in out.iterdir():
                _ = shutil.copy2(path, target / path.name)
            lines_ok = [f"kept {p.name} in {keep}/" for p in sorted(out.iterdir())]
            return Outcome(True, "\n".join(lines_ok))
    return Outcome(not lines, "\n".join(lines))


def inspect_wheel(wheel: Path, version: str) -> list[str]:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        metadata = archive.read(f"gpframe-{version}.dist-info/METADATA").decode()
    problems = [
        f"wheel lacks {name}" for name in REQUIRED_IN_WHEEL if name not in names
    ]
    problems += [
        f"wheel contains {name}"
        for name in sorted(names)
        if not name.startswith(("gpframe/", f"gpframe-{version}.dist-info/"))
    ]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if "Description-Content-Type: text/markdown" not in metadata:
        problems.append("the wheel metadata does not declare a Markdown description")
    if readme.strip() not in metadata:
        problems.append(
            "the wheel metadata does not carry README.md as its description"
        )
    requires = str(project()["requires-python"])
    if f"Requires-Python: {requires}" not in metadata:
        problems.append(f"the wheel metadata does not require Python {requires}")
    return problems


def inspect_sdist(sdist: Path, version: str) -> list[str]:
    prefix = f"gpframe-{version}/"
    with tarfile.open(sdist) as archive:
        names = {name.removeprefix(prefix) for name in archive.getnames()}
    return [f"sdist lacks {name}" for name in REQUIRED_IN_SDIST if name not in names]


def smoke_test(wheel: Path, tmp: Path) -> list[str]:
    """依存なしの、きれいな venv に wheel を入れて動かす。"""
    env = tmp / "venv"
    venv.EnvBuilder(with_pip=True).create(env)
    python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    install = subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--quiet",
            "--no-deps",
            "--no-index",
            str(wheel),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if install.returncode != 0:
        return ["installing the wheel failed:\n" + install.stdout + install.stderr]
    # リポジトリの src を読まないよう、別のディレクトリで動かす。
    run = subprocess.run(
        [str(python), "-I", "-c", SMOKE],
        cwd=tmp,
        capture_output=True,
        text=True,
        check=False,
    )
    if run.returncode != 0 or run.stdout.strip() != "gpframe ok":
        return ["the installed wheel does not work:\n" + run.stdout + run.stderr]
    return []


# ---------------------------------------------------------------- main


CHECKS: dict[str, Callable[[Options], Outcome]] = {
    "docs": check_docs,
    "format": command(PYTHON, "-m", "ruff", "format", "--check", "."),
    "lint": command(PYTHON, "-m", "ruff", "check", "."),
    # 型検査は、検査を走らせている Python の環境で行う(CI でもローカルでも同じ)。
    "types": command(PYTHON, "-m", "basedpyright", "--pythonpath", PYTHON),
    "types-tests": command(
        PYTHON, "-m", "basedpyright", "--pythonpath", PYTHON, "-p", "tests"
    ),
    "tests": command(PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider"),
    "dist": check_dist,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="gpframe のすべての検査をまとめて走らせる。"
    )
    _ = parser.add_argument(
        "checks", nargs="*", help=f"走らせる検査(省略時はすべて): {' '.join(CHECKS)}"
    )
    _ = parser.add_argument(
        "--tag", help="dist: リリースのタグ。v<version> と一致すること"
    )
    _ = parser.add_argument(
        "--dist-dir", help="dist: 確かめた配布物をこのディレクトリに残す"
    )
    args = parser.parse_args(argv)
    names = cast("list[str]", args.checks) or list(CHECKS)
    options = Options(
        tag=cast("str | None", args.tag), dist_dir=cast("str | None", args.dist_dir)
    )
    unknown = [n for n in names if n not in CHECKS]
    if unknown:
        parser.error(f"unknown checks: {' '.join(unknown)}")
    failed: list[str] = []
    for name in names:
        started = time.monotonic()
        outcome = CHECKS[name](options)
        elapsed = time.monotonic() - started
        mark = "ok" if outcome.ok else "FAIL"
        print(f"{name}: {mark} ({elapsed:.1f}s)", flush=True)
        if not outcome.ok:
            failed.append(name)
            print(outcome.output.rstrip(), flush=True)
        elif outcome.output and name == "dist":
            print(outcome.output.rstrip(), flush=True)
    if failed:
        print(f"failed: {' '.join(failed)}", flush=True)
        return 1
    print("all checks passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
