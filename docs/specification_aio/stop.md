<!-- Published from devdocs/canonical_documents/specification_aio/stop.md sha256:dfbdf8b17849e5762485260b56a808b0aa318fff1f878a9b14b8a43c94deb76a. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# Async stop

Rules on stop requests and delivery of cancellation in the asynchronous API, how a stop propagates, and stop callbacks.

## ASTOP_001

In the asynchronous API, a stop is performed by cancelling asyncio tasks. The cancellation arrives at the routine's next await point (`await`) as `asyncio.CancelledError`. This is the stop mechanism of the asynchronous API, and it differs from the mechanism of the synchronous API, which is "set a flag and have the routine check it."

title: Stop is cancellation

level: INFORMATIVE

## ASTOP_002

`AsyncSession.stop()` must record the stop request, cancel the tasks of all running frames of that session, and also recursively request a stop from the sub-sessions opened inside those frames.

title: Stop cancels every frame

level: MUST

## ASTOP_003

gpframe cancels the task of a frame at most once. No matter how many times `stop()` is called, an additional cancellation must not be sent to a routine that has caught the cancellation and is cleaning up.

title: A frame is cancelled at most once

level: MUST NOT

## ASTOP_004

A sub-session opened after the request, inside a frame of a session that has been requested to stop, must already be requested to stop at the moment it is opened.

title: Sub-sessions opened after a stop

level: MUST

## ASTOP_005

`stop()` is not a coroutine, and it returns without waiting for frames to end or for stop callbacks to complete. It may be called from any thread. Calling it two or more times results in the same state as calling it once. A stop request cannot be cancelled.

title: Stop is a thread-safe request

level: MUST

related: [ALIMIT_008](limits.md#alimit_008)

## ASTOP_006

`AsyncContext.stopping` returns `True` if a stop has been requested from the frame's session. A routine that has caught a cancellation uses it to check whether the cancellation came from a stop request.

title: Observing the stop request

level: MUST

## ASTOP_007

The asynchronous API provides no equivalent of `wait_stop()` from the synchronous API. A stop arrives at any await point as a cancellation, so there is no need to wait only for a stop.

title: No wait_stop in the async API

level: INFORMATIVE

## ASTOP_008

A routine should not swallow `asyncio.CancelledError`. Even when it catches the error for cleanup, it should re-raise it after the cleanup or end by returning a value. If the routine keeps running after catching it, the frame may become a stuck frame.

title: Writing cancellable routines

level: SHOULD

related: [AFRAME_004](frame.md#aframe_004), [ALIMIT_003](limits.md#alimit_003)

## ASTOP_009

The session itself requests a stop only when an exception occurs inside the `async with` block (including cancellation of the owner task itself), and when stuck frames remain after the wait at exit.

title: Implicit stop requests

level: MUST

related: [ASESSION_010](session.md#asession_010)

## ASTOP_010

`AsyncContext.on_stop(callback)` registers a synchronous callable that takes no arguments as a stop callback of the frame, and returns a `gpframe.aio.StopHandle` for cancelling the registration. Its main use is to register how to stop work that cancellation does not stop (such as blocking work running in `asyncio.to_thread()`).

title: Registering a stop callback

level: INFORMATIVE

related: [ALIMIT_006](limits.md#alimit_006)

## ASTOP_011

Coroutine functions, and anything that returns a coroutine when called, cannot be registered as stop callbacks. Registration raises `TypeError`. Stop callbacks are limited to synchronous callables that finish quickly.

title: Stop callbacks are synchronous

level: MUST

## ASTOP_012

Stop callbacks must be called when a stop is requested from the frame's session, regardless of the path of the request. Each registration is called at most once.

title: When stop callbacks run

level: MUST

## ASTOP_013

Stop callbacks must be called on the thread of the session's event loop, in the order in which they were registered. In addition, they are called before the cancellation of that frame reaches the routine. This ensures that, by the time the routine starts cleaning up, notification of how to stop has already been delivered.

title: Where and when stop callbacks run

level: MUST

## ASTOP_014

A stop callback registered when a stop has already been requested must be called the next time the event loop runs after the registration. In this case, the cancellation has already reached the routine, so the order of ASTOP_013, "call before the cancellation," does not hold.

title: Registering after a stop request

level: MUST

## ASTOP_015

After a frame's routine has ended, stop callbacks of that frame that have not yet been called must not be called.

title: Callbacks end with the routine

level: MUST NOT

## ASTOP_016

After `StopHandle.cancel()` is called, that stop callback must not be called. A cancelled registration must be removed from the frame, and no reference to the callback must remain. This ensures that registrations do not accumulate even if registration and cancellation are repeated inside a long-running frame. `cancel()` after the callback has already been called, or after the frame has ended, does nothing.

title: Cancelling a registration

level: MUST

## ASTOP_017

If a stop callback raises an exception, the exception must be recorded in `AsyncFrame.stop_errors`, and the frame must be made broken. The remaining stop callbacks of that frame and the cancellation of the frame still proceed.

title: Errors in stop callbacks

level: MUST

related: [AFRAME_003](frame.md#aframe_003)

## ASTOP_018

Stop callbacks are called on the event loop's thread, so they must not block. If they block, all guarantees are lost, per ALIMIT_002.

title: Stop callbacks must not block

level: MUST NOT

condition: When writing stop callbacks.

related: [ALIMIT_001](limits.md#alimit_001), [ALIMIT_002](limits.md#alimit_002)

## ASTOP_019

`AsyncSession.stop()` must be callable regardless of the session's state, even before it is opened with `async with` or after it is closed. If it is called before the session is opened, the session is already requested to stop when it is opened, and `spawn()` inside it returns stopped frames. To stop a root session from another thread, pass a reference to a session created in advance, as in STOP_020 of the synchronous API.

title: Stopping a session in any state

level: MUST

related: [ASESSION_005](session.md#asession_005), [AFRAME_015](frame.md#aframe_015)
