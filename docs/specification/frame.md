<!-- Published from devdocs/canonical_documents/specification/frame.md sha256:bb1f4db0d45fc9445aa93d00d20e49c083fbb2c92ad4f53628b825837a3aabdc. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# Frame

Rules on frame states, receiving return values and exceptions, and acknowledgement of failures.

## FRAME_001

A frame starts as `running` (except for the stopped frames of FRAME_012) and ends exactly once. An ended frame is exactly one of succeeded, broken, or stopped, and its state must not change after it ends.

| State | Meaning |
| --- | --- |
| succeeded | The routine ended and there is no failure |
| broken | There is a failure, and acknowledgement is required |
| stopped | It was spawned in a session for which a stop had been requested, so it ended without calling the routine (FRAME_012) |

A broken frame is an ended frame to which any of the following applies.

- The routine ended with an exception
- A sub-session opened inside the frame ended incomplete
- A stop callback of the frame raised an exception

A frame that ended after calling the routine and to which none of these applies is succeeded.

title: Frame states

level: MUST

## FRAME_002

If a sub-session opened inside a frame was incomplete, that frame must be a broken frame even if the routine returned a value.

title: Incomplete sub-sessions break the frame

level: MUST

## FRAME_003

`Frame.result(timeout)` must wait up to `timeout` seconds for the frame to end. If the frame has ended, it returns the return value of the routine or re-raises the exception that the routine raised. For a stopped frame, it raises `FrameStoppedError`. If the frame does not end in time, it raises `TimeoutError`. If `timeout` is `None`, it waits until the frame ends.

title: Waiting for the result

level: MUST

## FRAME_004

If the routine returned a value, `result()` returns that value even when a sub-session was incomplete or a stop callback raised an exception.

title: Result of a broken frame without a routine error

level: MUST

## FRAME_005

Calling `result()` or reading `error` must not count as acknowledging a failure.

title: Reading a result does not acknowledge

level: MUST NOT

## FRAME_006

`Frame.error` returns the exception if the routine ended with an exception, and `None` otherwise. It also returns `None` while the frame is running.

title: Routine error

level: MUST

## FRAME_007

`Frame.incomplete` returns the report of the sub-sessions that ended incomplete inside the frame. If there were several incomplete sub-sessions, it returns a single report that concatenates their `broken`, `stuck`, and `errors` in the order in which they ended. If there were none, it returns `None`.

title: Report of incomplete sub-sessions

level: MUST

## FRAME_008

A failure is acknowledged with `ignore()` or `escalate(reason)`. Only ended broken frames that are not yet acknowledged can be acknowledged.

title: Acknowledgement

level: MUST

## FRAME_009

`ignore()` and `escalate()` on a frame that cannot be acknowledged must raise `FrameStateError` without changing the state of the frame.

title: Rejected acknowledgement

level: MUST

condition: The frame is running, succeeded, stopped, or already acknowledged.

## FRAME_010

No means is provided to withdraw an acknowledgement once given or to replace it with a different acknowledgement. An acknowledgement is treated as the final decision made on the spot by the person who saw the failure.

title: Acknowledgement is final

level: INFORMATIVE

## FRAME_011

If the routine ends with a `BaseException` other than `Exception` (such as `KeyboardInterrupt`), it must also be recorded as a failure of the frame, and the frame must become a broken frame.

title: Non-Exception failures

level: MUST

## FRAME_012

The frame that `spawn()` returns on a session for which a stop has been requested must be a stopped frame that is returned in the ended state without calling the routine and without creating a thread.

- `stopped` returns `True`, and `running` and `succeeded` return `False`.
- `error` and `incomplete` are `None`, and `stop_errors` is empty.
- It is not a broken frame, so it does not require acknowledgement. It is also not included in the session's judgement at exit.

A stop is a normal outcome that results from having asked for it, and work that was about to start while things were stopping is not a failure. Even if a stop arrives between checking for a stop and spawning, it does not become an exception.

title: Frames spawned after a stop

level: MUST

## FRAME_013

An ended frame must release its references to the routine and its arguments. It keeps the return value, the exception, the report, and the exceptions of the stop callbacks. This is to prevent things passed as arguments (such as sockets and buffers) from staying unreleased for as long as someone keeps the frame's handle. However, what the traceback of a kept exception refers to (the local variables at the time the exception occurred) remains together with that exception.

title: Releasing the routine

level: MUST

## FRAME_014

`Frame.wait(timeout=None)` must wait up to `timeout` seconds for the frame to end, and return `True` if it has ended or `False` on timeout. If `timeout` is `None`, it waits until the frame ends.

- It does not raise an exception, regardless of how the frame ended (for a stopped frame, it returns `True` immediately).
- It does not count as acknowledging a failure (same as FRAME_005).

Use it to wait only for the end, regardless of how it ends, as in "when one ends (successfully or with a failure), stop the other." The result is determined with `result()`, and the handling of failures with acknowledgement.

title: Waiting for a frame to end

level: MUST

## FRAME_015

A stopped frame does not call the routine, so the responsibility for cleaning up what was passed as arguments (such as an accepted socket) remains with the caller of `spawn()`. When passing something that needs cleanup, check the result of `spawn()`.

```python
frame = clients.spawn(handle, conn)
if frame.stopped:
    conn.close()  # It does not run, so close it yourself
```

title: Arguments of a stopped frame

level: INFORMATIVE
