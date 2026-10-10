<!-- Published from devdocs/canonical_documents/CHANGELOG.md sha256:e730c2a1ebc048da1871f5223fbd88e884ef1d3bef3bb77e87c1253e99d838c4. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# gpframe Changelog

Records the changes in each version of `gpframe`.

## V0_1_0

The first version after discarding the old implementation, shrinking the design and rebuilding it from scratch. It is not backward compatible with the `0.0.x` releases.

The old design tried to take on everything at once: unifying thread and process execution, typed messages over four channels, and lifecycle handlers. It grew too large, and the implementation could not keep up. This version keeps only the two ideas at the core of the old design, "do not swallow failures" and "report work that did not stop", together with the consistency rules worked out for messages (a fixed type, initialization at creation, atomic updates). Everything else is left to the standard library and Python's own syntax.

version: 0.1.0

Added:

- Added sessions opened with `gpframe.session()` and frames started with `spawn()`. A frame holds the return value of its routine, which can be received with `result()`.
- Added acknowledging failed frames with `ignore()` / `escalate()`. When the root session ends, `escalate()`d failures are raised as `SessionFailed` (an `ExceptionGroup`), and unmarked failures are reported with `FrameWarning`. With `strict=True`, unmarked failures are raised too.
- Added cooperative stop (`stop()`, `Context.stopping`, `Context.wait_stop()`), and a mechanism that cuts off the wait at `timeout` seconds when a session ends and reports frames that did not stop.
- Added sub-sessions with `Context.session()`. An incomplete sub-session attaches its report to the owner frame, and the final judgement is made by the root session.
- Added the stop callback `Context.on_stop()` for stopping work that blocks. A callback is called once, in another thread; its exceptions are recorded in `Frame.stop_errors` and make the frame broken. A registration can be cancelled with `StopHandle.cancel()`.
- Added `Session.wait_broken()`, which waits for the first failure. Code that connects long-running components and stops everything when any one of them fails can be written without polling. With `idle=True`, it keeps waiting for a failure or a stop request even when no frame is running.
- Added `Frame.wait()` and `AsyncFrame.wait()`, which wait for the end of a frame however it ends.
- A session lets go of frames that the judgement no longer needs (succeeded, stopped, `ignore()`d), and a frame that has ended lets go of its routine and arguments. Even a long-lived session that starts a frame for each request does not pile up memory.
- Added `Shared`, a shared cell whose type and initial value are decided at creation.
- Added `Channel`, which passes values between frames in order. Receiving ends its wait on a stop request, so writing a receiving loop is enough to get a worker that can be stopped. With a capacity limit `maxsize`, `put(item, ctx)` waits until there is space, and a stop request or `close()` ends the wait.
- `spawn()` on a session that has been requested to stop returns a stopped frame without calling the routine (in both the synchronous and the asynchronous API). Work that was about to start while things were stopping is not made a failure.
- Added `tools/devwatch.py`, a development watcher written with gpframe; `examples/chat.py`, an example chat server written with `gpframe.aio`; and `examples/logstats.py`, an example log aggregation pipeline connected by `Channel`s.
- Added the asynchronous API `gpframe.aio`, which runs frames as tasks on an asyncio event loop. It is an independent API that shares no types with the synchronous API; a stop is done by cancelling tasks, and a frame that ended because of a stop request is counted not as a failure but as stopped.
- Added the health check `gpframe.aio.monitor()`, which detects stalls of the loop from a thread outside the loop and reports them.
- Added the behavior to be kept as `shikumi-contrace` contracts in `contract/`, and tied every clause to tests.
- Added README, Project Status and CHANGELOG to `devdocs/` as canonical sources of `shikumi-devdoc`.
- Added English published documents translated from the canonical documents, at the root of the repository (README, STATUS, CHANGELOG) and in `docs/` (Specification). `scripts/published_docs.py` confirms that the translations do not diverge from the canonical documents.
- Added `tools/check.py`, which gathers every check, and GitHub Actions CI (`ci.yml`) and release (`release.yml`) workflows. A release passes the same checks as CI and is then published with PyPI Trusted Publishing.
- Added the rules of behavior as the Specification: 6 documents for the synchronous API (session, frame, stop, waiting, `Shared`, `Channel`) and 6 for the asynchronous API (constraints and limits, frame, session, stop, waiting, health check). Each clause of the contracts points to the rule it is based on.

Changed:

- Changed the supported Python to `>=3.11`.

Removed:

- Removed the whole implementation and API of the `0.0.x` releases. Frame builders such as `create_frame()`, the distinction between root and sub frames and sessions, `FrameResult`, and the marking methods have been replaced by the new API of sessions and frames.
- Removed the four-channel messages (`environment` / `request` / `common` / `local`). Settings are routine arguments, stop instructions are `stop()`, passing values is `Channel`, results are frames' return values, and shared state is `Shared`.
- Removed lifecycle handlers (`on_open` / `on_start` / `on_end` / `on_redo` / `on_exception` / `on_close`). Write them with `try` / `finally`, `while` and `except` inside routines.
- Removed execution in subprocesses and the inter-process communication for it.
- Removed `design/`, which held drafts and specifications of the old design, and the old tests.
