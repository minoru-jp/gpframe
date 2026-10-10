<!-- Published from devdocs/canonical_documents/specification_aio/session.md sha256:ae5fec85a7c805a46cbb9abac29e80cef1b18058490ccf6763dccddfedf275f3. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# Async session

Rules on opening and closing asynchronous sessions, type separation from the synchronous API, spawning frames, judgement at exit, and sub-sessions.

## ASESSION_001

A root asynchronous session is created with `gpframe.aio.session(timeout, strict)`, and a sub-session inside a frame is created with `AsyncContext.session(timeout)`. Both are opened and used with `async with`.

title: Creating sessions

level: INFORMATIVE

## ASESSION_002

The asynchronous API has its own types in `gpframe.aio`, and they must not be mixed with the types of the synchronous API. The types of the asynchronous API are `AsyncSession`, `AsyncFrame`, `AsyncContext`, `AsyncSessionReport`, `AsyncSessionFailed`, `AsyncIncompleteSessionError`, `gpframe.aio.StopHandle`, and the health check types `LoopMonitor`, `LoopStall`, `LoopRecovery`, and `HealthWarning`.

Only types that do not depend on the execution model are shared with the synchronous API. These are `Shared`, `FrameWarning`, and the exceptions that do not hold a frame (`GpFrameError`, `SessionStateError`, `FrameStateError`, `FrameStoppedError`, `FrameAbortedError`, `DeclaredTypeError`). `Channel` is a component of the synchronous API only, and it is not used in the asynchronous API.

title: Separation from the synchronous API

level: MUST

## ASESSION_003

An asynchronous session can be opened with `async with` only once. A second attempt raises `SessionStateError`. It cannot be opened with a synchronous `with`.

title: A session is entered once

level: MUST

## ASESSION_004

`timeout` must be `None` or a number greater than or equal to 0. A negative number is rejected with `ValueError` when the session is created.

title: Timeout values

level: MUST

## ASESSION_005

`spawn()` can be used only on an open session. Before the session is opened or after it is closed, `spawn()` must raise `SessionStateError` without creating a frame. After a stop has been requested, it must return a stopped frame without creating a task (AFRAME_015). The check of ASESSION_006 is performed even after a stop.

title: Spawning needs an open session

level: MUST

related: [ALIMIT_007](limits.md#alimit_007), [AFRAME_015](frame.md#aframe_015)

## ASESSION_006

The `fn` of `spawn(fn, *args, name=None)` must be a coroutine function (`inspect.iscoroutinefunction()` is true). Otherwise, `spawn()` raises `TypeError` without starting a frame. This is because calling a synchronous function on the event loop could block the event loop.

title: Routines are coroutine functions

level: MUST

related: [ALIMIT_001](limits.md#alimit_001)

## ASESSION_007

`spawn()` must create a task on the session's event loop and run `await fn(context, *args)` inside that task. Only positional arguments are passed to the routine. `spawn()` itself is not a coroutine, and it returns an `AsyncFrame` immediately.

title: Running a routine

level: MUST

## ASESSION_008

If `name` is omitted, the frame's name is the routine's `__name__`, or the type name if there is no `__name__`. The name is for logs and reports, and names may be duplicated.

title: Frame names

level: MUST

## ASESSION_009

`broken()` must return only the broken frames that are not yet acknowledged, in the order in which they were spawned. It must not include running, succeeded, stopped, or acknowledged frames.

title: Listing unacknowledged failures

level: MUST

related: [AFRAME_001](frame.md#aframe_001), [AFRAME_012](frame.md#aframe_012)

## ASESSION_010

When exiting `async with`, the session must proceed in the following order.

1. If an exception occurred inside the `async with` block (including cancellation of the owner task itself), request a stop.
2. Wait up to `timeout` seconds for all frames to end.
3. Move to the closed state, and treat frames that have not yet ended as stuck frames.
4. If there are stuck frames, request a stop and detach them without waiting.
5. For a root session, perform the judgement at exit. For a sub-session, report to the owner frame.

title: Exit procedure

level: MUST

related: [ALIMIT_003](limits.md#alimit_003), [ALIMIT_004](limits.md#alimit_004)

## ASESSION_011

If the task that is running `__aexit__` is itself cancelled again during the wait in step 2, the wait ends there and the session proceeds to step 3 and later. Responding to cancellation takes priority over completing the wait.

title: Cancellation while waiting at exit

level: MUST

## ASESSION_012

If there are stuck frames, the root session must emit a `FrameWarning` that names them.

title: Reporting stuck frames

level: MUST

## ASESSION_013

At exit, the root session must handle broken frames according to their acknowledgement, as follows. It does nothing for stopped frames.

| Acknowledgement | Result |
| --- | --- |
| `ignore()` called | Do nothing |
| `escalate()` called | Include in the raised `AsyncSessionFailed` |
| Unacknowledged (`strict=False`) | Emit a `FrameWarning` that names the frame |
| Unacknowledged (`strict=True`) | Include in the raised `AsyncSessionFailed` |

An unacknowledged broken frame must not be discarded without a warning or an exception.

title: Judgement at the root

level: MUST

related: [AFRAME_002](frame.md#aframe_002), [AFRAME_012](frame.md#aframe_012)

## ASESSION_014

`AsyncSessionFailed` is an `ExceptionGroup`, and it must hold one exception for each frame that is subject to raising, in the order in which the frames were spawned. The `frames` attribute holds the corresponding frames in the same order. The exception for each frame is determined in the following order of priority.

1. If the routine ended with an `Exception`, that exception.
2. If the routine ended with any other `BaseException` (including a cancellation that gpframe did not request), a `FrameAbortedError` whose `__cause__` is that exception.
3. If a stop callback raised an exception, the first such exception (wrapped in the same way as in step 2 if it is not an `Exception`).
4. Otherwise (if a sub-session was incomplete), an `AsyncIncompleteSessionError` that holds the report.

The results of splitting with `split()` and `subgroup()` are also `AsyncSessionFailed`, and they hold only the frames that correspond to the remaining exceptions.

title: Contents of AsyncSessionFailed

level: MUST

related: [AFRAME_003](frame.md#aframe_003)

## ASESSION_015

If the exception inside the `async with` block is not `asyncio.CancelledError` and it coincides with raising `AsyncSessionFailed`, the session raises `AsyncSessionFailed` and keeps the exception from the block as its `__context__`. If `AsyncSessionFailed` is not raised, the exception from the block is re-raised as is.

title: Body errors and AsyncSessionFailed

level: MUST

## ASESSION_016

If the exception inside the `async with` block is `asyncio.CancelledError` (when the owner task itself was cancelled), `__aexit__` must re-raise it and must not replace it with `AsyncSessionFailed`. The failures that would otherwise have been raised in `AsyncSessionFailed` are reported with a `FrameWarning` that names them. This is to avoid breaking how cancellation propagates in asyncio.

title: The owner's cancellation takes precedence

level: MUST

## ASESSION_017

A sub-session must not emit warnings and must not raise its own exceptions when exiting `async with`. Only the root session makes the final judgement.

title: Sub-sessions do not judge

level: MUST NOT

## ASESSION_018

A sub-session is incomplete if any of the following applies, and it must attach its report (`AsyncSessionReport`) to the owner frame.

- There is a broken frame that has not been `ignore()`d (including frames that have been `escalate()`d)
- There is a stuck frame
- An exception occurred inside the `async with` block. However, this does not include `asyncio.CancelledError` caused by a stop request from the session of the owner frame

The report's `broken`, `stuck`, and `errors` correspond to the three items above, respectively. A stopped frame falls under none of them.

title: Incomplete sub-sessions

level: MUST

related: [AFRAME_003](frame.md#aframe_003), [AFRAME_010](frame.md#aframe_010)

## ASESSION_019

An exception raised inside the `async with` block of a sub-session must be re-raised as is, whether or not it was recorded in the report.

title: Body errors in sub-sessions

level: MUST

## ASESSION_020

If an owner frame is `ignore()`d at the root, the failures that occurred under that frame are also forgiven together.

title: Ignoring a parent forgives its children

level: INFORMATIVE

## ASESSION_021

A session must not keep frames that are no longer needed for the judgement at exit and the report (succeeded, stopped, and `ignore()`d broken frames). It releases them when they end, or when `ignore()` is called. Same as SESSION_019 of the synchronous API.

title: A session keeps only what the judgement needs

level: MUST

related: [AFRAME_016](frame.md#aframe_016)
