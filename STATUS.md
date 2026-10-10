<!-- Published from devdocs/canonical_documents/STATUS.md sha256:da68802fe79f98b0f00f8bd28a165d6c587595b292d48fae9632a8cfe7a752c0. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# gpframe Project Status

This document describes the current state of `gpframe` and its future direction as seen from now.
Changes that actually happened in the past belong to the CHANGELOG.

## STATUS_001

The current development stage is Alpha. The current version is `0.1.0`, and it has not been published on PyPI yet. The latest release on PyPI is `0.0.34`, the old implementation from before the rewrite.

title: Development stage

## STATUS_002

The supported Python version range is `>=3.11`, because `SessionFailed` uses the standard `ExceptionGroup` and the typing of `spawn()` uses `TypeVarTuple`. There are no runtime dependencies.

title: Supported Python

## STATUS_003

Execution covers threads (the synchronous `gpframe`) and asyncio tasks (the asynchronous `gpframe.aio`). Processes are not covered. The synchronous API provides the following.

- Sessions opened with `gpframe.session()`, and frames started with `spawn()`. `spawn()` after a stop returns a stopped frame without calling the routine
- Acknowledgement of failed frames (`ignore()` / `escalate()`) and the judgement when a session ends
- Cooperative stop (`stop()` / `ctx.stopping` / `ctx.wait_stop()`) and reporting of frames that did not stop
- Stop callbacks for stopping work that blocks (`ctx.on_stop()`)
- `wait_broken()`, which waits for the first failure. With `idle=True`, it keeps waiting for failures in a session whose frames come and go
- `Frame.wait()`, which waits for the end of a frame however it ends
- Letting go of frames that have ended (succeeded, stopped, `ignore()`d) and of their arguments, so memory does not pile up even in a session that stays open for a long time
- Sub-sessions inside frames, and reports of incomplete sub-sessions to their owner frames
- `Shared`, a shared cell with a fixed type
- `Channel`, which passes values between frames in order and whose sending and receiving waits end on a stop. With a capacity limit (`maxsize`), the sender waits for space

When an `async def` routine is used with the synchronous API, it runs on a dedicated event loop in the frame's thread. Checking for a stop then means polling `ctx.stopping`.

title: Scope

## STATUS_004

The Specification is the authoritative source for rules of behavior. The synchronous one is in `devdocs/canonical_sources/specification/`, and the asynchronous one in `devdocs/canonical_sources/specification_aio/`. The promises among them that tests keep are placed in `contract/` as `shikumi-contrace` contracts, and the shape of the public API is placed in `contract/ports/` as Protocols (`surface.py` for the synchronous API, `aio_surface.py` for the asynchronous API). There are 6 contracts for the synchronous API (`SessionContract`, `FrameContract`, `ContextContract`, `StopHandleContract`, `SharedContract`, `ChannelContract`) and 5 for the asynchronous API (`AsyncSessionContract`, `AsyncFrameContract`, `AsyncContextContract`, `AsyncStopHandleContract`, `LoopMonitorContract`).

pytest confirms three things: every clause is tied to at least one test; every clause points with `source` to the rule of the Specification it is based on; and the rule pointed to actually exists in the Specification.

pytest always runs with `--contrace-check` and treats every warning as an error. Therefore, if there is a structural problem in the contract assets, or a warning about an unacknowledged failure, the tests fail.

title: Contracts and tests

## STATUS_009

All checks are gathered in `tools/check.py`. There are seven: `docs` (the canonical documents and the published documents are up to date), `format`, `lint`, `types`, `types-tests`, `tests`, and `dist` (build an sdist and a wheel, `twine check --strict`, inspect their contents, and confirm that the wheel works in a clean venv without dependencies). `python tools/check.py` runs all of them, and listing names runs only some. The versions of the tools used for checking are fixed by the extras in `pyproject.toml` (`dev` includes all of them).

GitHub Actions consists of two workflows.

- `ci.yml`: on every push and pull request, runs `python tools/check.py` on Python 3.11, 3.12 and 3.13.
- `release.yml`: when a Release is published on GitHub, it first calls `ci.yml` as it is and passes the same checks. It then builds and checks the distributions with `python tools/check.py dist --tag <tag>` (also confirming that the tag matches `v<version>`), and publishes them with PyPI Trusted Publishing. No API token is used.

For Trusted Publishing, this repository, the workflow `release.yml` and the environment `pypi` must be registered as a Trusted Publisher on PyPI.

title: Checks, CI and release

## STATUS_010

The English published documents are made by translating the Japanese canonical documents. README, STATUS and CHANGELOG are at the root of the repository, and the Specification is in `docs/specification/` and `docs/specification_aio/`. The translation itself is not automated; `scripts/published_docs.py` checks the following mechanically (included in `tools/check.py docs`).

- Every canonical document has a published document, and there are no extra published documents
- The stamp at the top of each published document matches the SHA-256 of the current canonical document. When a canonical document changes, the check fails until it is re-translated and stamped again with `python scripts/published_docs.py stamp <published document>`
- The Python code examples are the same as in the canonical document, apart from comments and docstrings
- The rule headings of the Specification are the same, in the same order and number
- The targets of links exist

title: Published documents

## STATUS_005

Static analysis is clean for `ruff format --check .`, `ruff check .`, and both BasedPyright configurations.

- Ruff is pinned to 0.16.10 with Python 3.11 as the target version. Linting is based on the default rule set of the pinned version.
- BasedPyright 1.40.2 checks `src/gpframe`, `contract/ports`, `tools` and `examples` in `recommended` mode with 0 errors / 0 warnings. Only two diagnostics are disabled: `reportImplicitOverride`, because `typing.override` is available from Python 3.12; and `reportPrivateUsage`, because a leading `_` is treated as the public boundary outside the package, and the session, frame and context in the same module handle each other's internal state.
- `tests/pyrightconfig.json` checks the tests, contracts and canonical sources of the documents as users of the API in `standard` mode, with 0 errors / 0 warnings.

Local suppressions needed to keep the runtime meaning (`pyright: ignore` and `noqa`) have their reasons written next to them.

title: Static analysis

## STATUS_006

`@binds[Subject](Implementation)` in the tests also serves to confirm by type checking that the implementation satisfies the Protocols of the public API. However, with BasedPyright 1.40.2, for the argument type `T | Callable[..., T]` of `binds`, an intermediate result of comparing a class object with a Protocol is wrongly reused, and the conformance of `Context` and `Session`, which refer to each other, may be judged a failure.

As a workaround, at the top of each test module that uses `binds`, the implementation is assigned to a variable of type `Callable[..., Protocol]` so that its shape is confirmed first. It has been confirmed that deliberately breaking the implementation makes both this confirmation and `binds` report errors.

title: Known type-checker behavior

## STATUS_007

The asynchronous `gpframe.aio` runs frames as tasks on an event loop. It is an independent API that shares no types with the synchronous API, and a stop is done by cancelling tasks. A frame that ended because of a stop request becomes stopped and is not treated as a failure.

- Sessions opened with `aio.session()` and `spawn()` (coroutine functions only), and waits with `await` (`wait()`, `wait_broken()`, `AsyncFrame.result()`)
- Acknowledgement of failures and the judgement at exit. When the owner task itself is cancelled, the cancellation takes precedence and failures are reported with a warning
- Stop callbacks for work that cancellation does not stop (`ctx.on_stop()`)
- Sub-sessions inside frames
- The health check `aio.monitor()`, which detects stalls of the loop from a thread outside the loop and reports them

The Specification of the asynchronous API starts with the "Constraints and limits" document. It states, as inherent limitations rather than shortcomings of the design, that the guarantees of `timeout` and of reporting are lost for frames that block the loop, and that tasks ignoring cancellation are detached without guaranteed cleanup.

title: Async API

related: [ALIMIT_001](docs/specification_aio/limits.md#alimit_001), [ALIMIT_002](docs/specification_aio/limits.md#alimit_002)

## STATUS_008

gpframe's own development uses tools built with gpframe (dogfooding). `tools/devwatch.py` is a tree of workers: a worker that detects changes to files, a worker that runs document generation and the checks (with a sub-session for each check), and a worker that serves the generated documents. It is written using only the public API. `python tools/devwatch.py --once` generates the documents and then runs the checks of `tools/check.py` used by CI (except `dist`) in parallel.

Writing this tool revealed two problems: `spawn()` after a stop turned an ordinary stop into a failure, and there was no way to end a wait for values passed between workers on a stop. They were solved with stopped frames and with `Channel`, respectively.

The asynchronous API is tried out in `examples/chat.py`, a line-based chat server that starts a frame for each connection. Failures of single connections are `ignore()`d at the accepting level, and the whole runs inside the health check. This example revealed that frames that had ended kept piling up in the session (about 18MB for 4000 connections), that `wait_broken()` could not wait when no frame was running, and that there was no way to wait for the end of a frame however it ended. They were solved by letting go of frames, by `idle=True`, and by `wait()`, respectively.

`Channel` is tried out in `examples/logstats.py`, a log aggregation pipeline whose reading, parsing and aggregating stages are connected by `Channel`s. When an upstream stage ends, it closes its outgoing `Channel` and lets the downstream end. This example revealed a bug where cancelled stop callback registrations remained in the frame (`Channel.get()` registers and cancels each time it waits), which was fixed. It also showed that with an unlimited `Channel`, almost the whole input piles up when the reader is fast (112MB for one million lines), so a capacity limit and `put(item, ctx)`, which waits for space, were added (24MB with a limit of 20).

title: Dogfooding

## NOTICE_001

Adding execution in processes is being considered, limited to passing arguments and return values (both picklable). In that case `Shared` cannot be used across processes.

title: Possible process execution

kind: General

condition: After the thread API has settled.

## NOTICE_003

Forced termination of threads is not provided. gpframe's responsibility ends at reporting frames that do not stop as stuck frames.

title: No forced thread termination

kind: General

condition: Continued as a policy.
