<!-- Published from devdocs/canonical_documents/specification_aio/limits.md sha256:dda319b092ed7224c0bfa6045ff53563d2432566bf115a3400c777eb7605bc08. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# Constraints and limits

This document defines up front what the asynchronous API cannot guarantee. The constraints and limits described here are not shortcomings of the design. They are inherent, and they come from the execution model: running cooperatively on a single event loop. All rules in the other documents assume that the constraints in this document are followed.

Rather than carrying the limits silently, gpframe.aio states them, and then promises what it can promise within them.

## ALIMIT_001

A frame's routine and its stop callbacks must not block the event loop. Move blocking work out of the event loop, for example with `asyncio.to_thread()`.

title: Do not block the loop

level: MUST NOT

## ALIMIT_002

While the event loop is blocked, no mechanism that runs on the event loop can run. Therefore all of the following guarantees are lost, and gpframe does not even detect that the event loop was blocked.

- Ending a wait by `timeout`
- Delivery of a stop (cancellation) and calls to stop callbacks
- Reports of stuck frames, and the judgement at exit

Monitoring whether the event loop is responding is the role of a separate tool (the health check) that lies outside the guarantees of gpframe.aio. The rules for the health check are defined in the Health monitoring document (`health.md`).

title: A blocked loop voids the guarantees

level: INFORMATIVE

condition: When ALIMIT_001 is not followed.

## ALIMIT_003

There is no way to stop, from outside, a frame that catches cancellation and continues its work. gpframe reports such a frame as a stuck frame and detaches it from the session. gpframe does not guarantee whether a detached frame stops later, or whether its cleanup is performed.

title: Frames that ignore cancellation

level: INFORMATIVE

## ALIMIT_004

The task of a detached frame may keep running after the scope is exited. This intentionally breaks the principle of structured concurrency that "no subordinate tasks remain after the scope is exited." gpframe prefers to report the fact that a frame did not stop and move on, rather than keep waiting and stop the caller as well.

title: Detaching breaks structured concurrency on purpose

level: INFORMATIVE

## ALIMIT_005

If the task of a detached frame has not yet finished when the event loop shuts down, it may be destroyed under the normal rules of asyncio. gpframe does not guarantee cleanup at that time.

title: Pending tasks at loop shutdown

level: INFORMATIVE

## ALIMIT_006

gpframe does not track threads that a frame starts, for example with `asyncio.to_thread()`. Cancellation does not stop work inside a thread, so if it needs to be stopped, register how to stop it with a stop callback.

title: Threads started by a frame

level: INFORMATIVE

## ALIMIT_007

An asynchronous session belongs to the event loop that was running when it was opened with `async with`. Every operation except `stop()` must be performed from that event loop's thread. Operations from another thread or another event loop are rejected with `SessionStateError` when they can be detected.

title: A session belongs to one loop

level: MUST

## ALIMIT_008

A `stop()` called from another thread records the stop request immediately, but the cancellation and the stop callbacks are delivered the next time the event loop runs. If the event loop is blocked, they are delivered when it resumes. If the event loop is closed, they are not delivered.

title: Stopping from another thread

level: INFORMATIVE

condition: When `stop()` is called from a thread other than the event loop's thread.

## ALIMIT_009

Inside an asynchronous frame, you must not open a session of the synchronous API and wait on it. A wait in the synchronous API blocks the thread, which violates ALIMIT_001.

title: No synchronous sessions inside async frames

level: MUST NOT

## ALIMIT_010

Conversely, inside an `async def` routine that runs in a frame of the synchronous API, you may use an asynchronous session. This is because that routine runs on a dedicated event loop in the frame's thread.

title: Async sessions inside synchronous frames

level: INFORMATIVE

## ALIMIT_011

`Shared` can also be used from asynchronous frames. However, it uses a thread lock internally, so when it contends for the same `Shared` with frames of the synchronous API, the event loop is blocked for a short time. The function passed to `apply()` should be even shorter than in the synchronous API.

title: Using Shared from async frames

level: SHOULD

## ALIMIT_012

Some calls that violate ALIMIT_001 can be found by static checks. For example, you should enable Ruff's ASYNC rules (such as ASYNC251, which flags `time.sleep()` inside an async function). However, only typical calls can be detected, and this does not guarantee that the event loop is not blocked.

title: Static checks for blocking calls

level: SHOULD

condition: When writing asynchronous routines and stop callbacks.
