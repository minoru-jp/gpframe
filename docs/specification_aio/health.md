<!-- Published from devdocs/canonical_documents/specification_aio/health.md sha256:8b7aca87577beb5a9bbca4e334fbe5f0c00074988ac4eb19e469699e69b3ea68. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# Health monitoring

Rules on the health check, which detects from outside the event loop that the event loop has stopped responding and reports it.

When the event loop is blocked, all of the session's guarantees (ending waits by timeout, stops, reports) are lost. The health check is a tool that lets users observe that condition. It does not restore the session's guarantees, and it does not release the block.

## AHEALTH_001

The health check does not make up for the guarantees lost in ALIMIT_002. It makes the loss of those guarantees observable. It runs independently of sessions and does not change the state of sessions.

title: Purpose and position

level: INFORMATIVE

related: [ALIMIT_002](limits.md#alimit_002)

## AHEALTH_002

A health check is created with `gpframe.aio.monitor(threshold=1.0, *, interval=None, on_stall=None, on_recover=None)`, and is opened and used with `async with`. It monitors the event loop that was running when it was opened. The unit of monitoring is the event loop, not the session.

title: Creating a monitor

level: INFORMATIVE

## AHEALTH_003

`threshold` must be a number of seconds greater than 0, and defaults to 1.0 seconds. `interval` must be greater than 0 and less than or equal to `threshold`, and defaults to `threshold / 4`. If these are not satisfied, `ValueError` is raised at creation. The values actually used can be read from `LoopMonitor.threshold` and `LoopMonitor.interval`.

title: Parameter values

level: MUST

## AHEALTH_004

A `LoopMonitor` can be opened with `async with` only once, and a second attempt raises `SessionStateError`. Multiple health checks may be opened on one event loop, and each runs independently.

title: Entering a monitor

level: MUST

## AHEALTH_005

The health check must measure responsiveness with the following two components.

- A heartbeat task that records the time on the event loop every `interval` seconds
- A watcher thread that, on a thread outside the event loop, measures the time elapsed since the last heartbeat (the lag) every `interval` seconds

When the lag exceeds `threshold` seconds, the event loop is considered to be in a stall.

title: Heartbeat and watcher

level: MUST

## AHEALTH_006

What the health check measures is the lag in the event loop's responses. It does not distinguish a stall caused by a single blocking call from overload caused by many pieces of work.

title: What is measured

level: INFORMATIVE

## AHEALTH_007

Detection of a stall is delayed by up to approximately `threshold + interval` seconds after the stall begins. Stalls shorter than `threshold` seconds are not reported.

title: Detection latency

level: INFORMATIVE

## AHEALTH_008

For each continuous stall, the detection of the stall must be reported only once. When the event loop becomes responsive again (when a heartbeat is recorded), recovery is reported only once, and the health check prepares to detect the next stall.

title: One report per stall

level: MUST

## AHEALTH_009

When a stall is detected, `on_stall` must be called with a `LoopStall`. `LoopStall` has the following values.

- `started`: The time when the last heartbeat was recorded (a `time.monotonic()` value)
- `detected`: The time when the stall was detected (same as above)
- `stack`: The stack of the event loop's thread at the time of detection (a sequence of strings). `None` if it cannot be obtained

If `on_stall` is omitted, a `HealthWarning` is emitted that contains the lag in seconds and the last line of `stack`. This ensures that a stall is not silently overlooked.

title: Reporting a stall

level: MUST

## AHEALTH_010

`LoopStall.stack` is a copy of the stack of the event loop's thread at the moment of detection, and the event loop may have moved on after the copy was taken. It is not guaranteed to point exactly at the location that caused the stall. It may be `None` on implementations other than CPython.

title: The stack is a best-effort snapshot

level: INFORMATIVE

## AHEALTH_011

When recovery is detected, `on_recover` must be called with a `LoopRecovery` (`started`, `recovered`, `duration`). If `on_recover` is omitted, nothing is done.

title: Reporting a recovery

level: MUST

## AHEALTH_012

`on_stall` and `on_recover` are called on the watcher thread. The event loop may be blocked, so a callback must not await asynchronous APIs on the event loop. Use only thread-safe operations (logging, `AsyncSession.stop()`, and so on).

title: Callbacks run on the watcher thread

level: MUST NOT

condition: When writing `on_stall` and `on_recover`.

related: [ALIMIT_007](limits.md#alimit_007)

## AHEALTH_013

A callback may call `AsyncSession.stop()`. However, per ALIMIT_008, the cancellation is delivered when the event loop resumes. The health check never stops a session automatically.

title: Stopping sessions from a callback

level: MAY

related: [ALIMIT_008](limits.md#alimit_008)

## AHEALTH_014

If a callback raises an exception, the exception must be recorded in `LoopMonitor.errors`, and a `HealthWarning` that contains it must be emitted. Monitoring continues afterward.

title: Errors in monitor callbacks

level: MUST

## AHEALTH_015

`LoopMonitor.stalled` returns `True` during a stall, and `LoopMonitor.lag` returns the number of seconds elapsed since the last heartbeat. Both may be read from any thread. They can be used to answer the state from an external health check endpoint (such as an HTTP liveness check) without relying on the event loop.

title: Querying the state

level: MUST

## AHEALTH_016

When exiting `async with`, the health check must stop the heartbeat task and the watcher thread. `on_stall` and `on_recover` must not be called after the exit.

title: Closing a monitor

level: MUST

## AHEALTH_017

If the blocking work does not release the GIL (as with some C extensions that run for a long time while holding the GIL), the watcher thread cannot run either, and detection is delayed until that work releases the GIL. This is an inherent limitation of the health check itself.

title: When the watcher cannot run

level: INFORMATIVE

## AHEALTH_018

`threshold` should be chosen to match the response lag that the application can tolerate. If it is too small, even short lags caused by garbage collection or temporary load are reported as stalls. The default of 1.0 seconds is a value for general use. It aims to find real blocks on the order of seconds (such as synchronous I/O mixed into asynchronous code, or loops with heavy computation) just by enabling the health check, without reporting normal fluctuations. As a guideline, use about 0.2 to 0.5 seconds for uses where responsiveness is important, and about 5 seconds for uses that include heavy work.

title: Choosing a threshold

level: SHOULD

## AHEALTH_019

Typical use is as follows.

```python
async with gpframe.aio.monitor() as monitor:  # Report stalls longer than 1 second
    async with gpframe.aio.session(timeout=10) as s:
        ...
```

The synchronous API has no health check. This is because frames of the synchronous API each run on their own thread, so even if one frame hangs, the session's waits and reports keep working.

title: Typical use

level: INFORMATIVE
