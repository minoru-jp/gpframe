<!-- Published from devdocs/canonical_documents/specification_aio/frame.md sha256:3370953018b7259359d2654e7548a9c1fcd8fe74a95edf00e9784755a9f25ca8. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# Async frame

Rules on asynchronous frame states, receiving results, and acknowledgement of failures.

## AFRAME_001

An asynchronous frame (`AsyncFrame`) starts in `running` (except for the stopped frame of AFRAME_015) and ends exactly once. An ended frame is exactly one of succeeded, stopped, or broken, and its state must not change after it ends.

| State | Meaning |
| --- | --- |
| succeeded | The routine returned a value and ended, and there is no failure |
| stopped | The frame ended by cancellation caused by a gpframe stop request, and there is no failure. Or, it was spawned after a stop and ended without calling the routine (AFRAME_015) |
| broken | There is a failure, and acknowledgement is required |

title: Frame states

level: MUST

## AFRAME_002

If the routine ends with `asyncio.CancelledError` after the frame's session has requested a stop, the frame is stopped. Stopping as a result of a requested stop is a normal outcome, so no acknowledgement is required.

title: Stopped frames

level: MUST

## AFRAME_003

An ended frame that matches any of the following is broken.

- The routine ended with an exception other than `asyncio.CancelledError`
- The routine ended with `asyncio.CancelledError` although the session had not requested a stop (a cancellation that gpframe did not request)
- A sub-session opened inside the frame ended incomplete
- A stop callback of the frame raised an exception

The last two also apply when the routine returned a value or ended in a way that counts as stopped, and they make the frame broken.

title: Broken frames

level: MUST

## AFRAME_004

If the routine catches `asyncio.CancelledError` and returns a value, the frame is succeeded (if there is no other failure).

title: Returning after catching cancellation

level: MUST

## AFRAME_005

`await AsyncFrame.result(timeout)` must wait up to `timeout` seconds for the frame to end, and then act as follows depending on the state in which it ended. If the frame does not end in time, it raises `TimeoutError`.

- If the routine returned a value, return that value (even if the frame is broken).
- If the frame is stopped, raise `FrameStoppedError`.
- If the routine ended with an exception, raise that exception. However, if that exception is `asyncio.CancelledError`, raise a `FrameAbortedError` whose `__cause__` is that exception.

title: Waiting for the result

level: MUST

## AFRAME_006

`result()` must not raise the frame's `asyncio.CancelledError` to the caller as is. This is because the caller's task would mistake it for its own cancellation.

title: Cancellation does not leak into the caller

level: MUST NOT

## AFRAME_007

Even if the caller waiting in `await result()` is cancelled, the frame must not be cancelled or stopped. Only the caller stops waiting.

title: Cancelling a waiter does not cancel the frame

level: MUST NOT

## AFRAME_008

`AsyncFrame.error` returns the exception if the routine ended with an exception (including a cancellation that gpframe did not request), and `None` otherwise. It returns `None` for stopped frames and for running frames.

title: Routine error

level: MUST

## AFRAME_009

`AsyncFrame.stopped` and `AsyncFrame.succeeded` each return `True` when the frame is in the corresponding state of AFRAME_001. While the frame is running, both return `False`.

title: State properties

level: MUST

## AFRAME_010

`AsyncFrame.incomplete` returns the reports (`AsyncSessionReport`) of sub-sessions that ended incomplete, concatenated in the order in which they ended, as a single report. If there are none, it returns `None`.

title: Report of incomplete sub-sessions

level: MUST

## AFRAME_011

Calling `result()` or reading `error` must not count as acknowledging a failure.

title: Reading a result does not acknowledge

level: MUST NOT

## AFRAME_012

A failure is acknowledged with `ignore()` or `escalate(reason)`. Only broken frames that are not yet acknowledged can be acknowledged. For running, succeeded, stopped, and already acknowledged frames, these methods must raise `FrameStateError` without changing the state.

title: Acknowledgement

level: MUST

condition: When `ignore()` or `escalate()` is called.

## AFRAME_013

Acknowledgement happens only once, and no means is provided to cancel it or to change it. This follows the same idea as the synchronous API.

title: Acknowledgement is final

level: INFORMATIVE

## AFRAME_014

If the routine ends with `KeyboardInterrupt` or `SystemExit`, the frame must be recorded as broken, and the exception must then be passed to asyncio without being swallowed. If an interrupt or exit request were stopped inside a frame, the program could no longer be stopped.

The passed exception propagates out of the event loop (for example, to the caller of `asyncio.run()`) under the normal rules of asyncio. Therefore, the session's exit processing may be performed as cancellation caused by the shutdown of the event loop (ASESSION_016). Because the exception is recorded in the frame and also delivered to the caller, asyncio's log message for "exceptions of tasks that were never retrieved" is not emitted.

title: Interrupts are not swallowed

level: MUST

## AFRAME_015

A frame returned by `spawn()` of a session that has been requested to stop must be a stopped frame that creates no task, does not call the routine, and is returned in the ended state.

- `stopped` returns `True`, and `running` and `succeeded` return `False`.
- `error` and `incomplete` are `None`, and `stop_errors` is empty.
- `await result()` raises `FrameStoppedError`.
- It is not broken, so no acknowledgement is required.

Following the same idea as FRAME_012 of the synchronous API, work that was about to start while things were stopping is not a failure.

title: Frames spawned after a stop

level: MUST

## AFRAME_016

An ended frame must release its references to the routine and its arguments. It keeps the return value, the exception, the reports, and the exceptions from stop callbacks (whatever an exception's traceback references remains together with that exception). Same as FRAME_013 of the synchronous API.

title: Releasing the routine

level: MUST

## AFRAME_017

`await AsyncFrame.wait(timeout=None)` must wait up to `timeout` seconds for the frame to end, without stopping the event loop, and return `True` if the frame has ended, or `False` if the time runs out.

- It raises no exception, regardless of how the frame ended (for a stopped frame, it returns `True` immediately).
- It does not count as acknowledging a failure.
- Even if the waiting caller is cancelled, the frame is not cancelled or stopped (same as AFRAME_007).

title: Waiting for a frame to end

level: MUST

## AFRAME_018

A stopped frame does not call its routine, so the responsibility for cleaning up what was passed as arguments (such as an accepted socket) remains with the side that called `spawn()`. Same as FRAME_015 of the synchronous API.

title: Arguments of a stopped frame

level: INFORMATIVE
