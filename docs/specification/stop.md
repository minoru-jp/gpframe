<!-- Published from devdocs/canonical_documents/specification/stop.md sha256:85c90ca5ee5f3260df3a92ef976ee14dd804e4ce24e00f70b130fee41bb8574a. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# Stop

Rules on stop requests, how a stop propagates, and stop callbacks.

## STOP_001

Every stop is cooperative. gpframe only requests a stop from frames; it provides no means to forcibly stop a thread. Whether to stop in response to the request is left to the routine, and frames that did not stop are reported as stuck frames.

title: Cooperative stop

level: INFORMATIVE

related: [SESSION_010](session.md#session_010)

## STOP_002

`Session.stop()` must request a stop from all frames of that session and from the sub-sessions opened inside those frames. The request to a sub-session propagates recursively to the sub-sessions inside it.

title: Stop propagates downward

level: MUST

## STOP_003

A sub-session opened, after the request, inside a frame of a session for which a stop has been requested must be in the stop-requested state at the time it is opened.

title: Sub-sessions opened after a stop

level: MUST

## STOP_004

`Session.stop()` must return without waiting for frames to end or for stop callbacks to complete. Calling it two or more times results in the same state as calling it once.

title: Stop is a request

level: MUST

## STOP_005

A stop request cannot be cancelled. A session for which a stop has once been requested never returns to the state in which no stop is requested.

title: Stop cannot be withdrawn

level: MUST

## STOP_006

`Context.stopping` must return `True` if a stop has been requested for the session of that frame.

title: Observing the stop request

level: MUST

## STOP_007

`Context.wait_stop(timeout)` waits up to `timeout` seconds for a stop to be requested. If a stop is requested, it must return `True` without waiting for `timeout`, and on timeout it must return `False`. If a stop has already been requested, it returns `True` immediately.

title: Waiting for a stop request

level: MUST

## STOP_008

A routine should use `Context.stopping` as the condition of its loops, and should use `Context.wait_stop()` instead of `time.sleep()` to wait.

title: Writing stoppable routines

level: SHOULD

## STOP_009

A session itself requests a stop only when an exception occurred inside the `with` block, or when stuck frames remain after the wait at exit.

title: Implicit stop requests

level: MUST

related: [SESSION_009](session.md#session_009)

## STOP_010

`Context.on_stop(callback)` registers a callable that takes no arguments as a stop callback of that frame, and returns a handle (`StopHandle`) for cancelling the registration.

Stop callbacks are for stopping operations that cannot check `ctx.stopping`. For example, a blocking `serve_forever()` is stopped by registering `server.shutdown`.

title: Registering a stop callback

level: INFORMATIVE

## STOP_011

A stop callback must be called when a stop is requested for the frame's session. The path of the request (`stop()`, propagation from the parent, or a request by the session itself) does not matter. A single registration is called at most once (how requests propagate follows STOP_002 and STOP_009).

title: When stop callbacks run

level: MUST

## STOP_012

A stop callback registered when a stop has already been requested must be called immediately after the registration, in the same way as when a request arrives. This is so that a request arriving between the check and the registration is not missed.

title: Registering after a stop request

level: MUST

## STOP_013

Stop callbacks must be called on a separate thread that is neither the thread that requested the stop nor the frame's thread. The stop callbacks of one frame are called one at a time, in the order in which they were registered. The order of calls between different frames is not specified. As stated in STOP_004, `stop()` does not wait for callbacks to complete.

title: Where stop callbacks run

level: MUST

## STOP_014

After a frame's routine has returned, the stop callbacks of that frame that have not yet been called must not be called. This is because the operation that should be stopped no longer exists.

title: Callbacks end with the routine

level: MUST NOT

## STOP_015

If the routine returns while a stop callback is being called, the frame must not end until that callback returns.

title: A frame waits for a running callback

level: MUST

related: [FRAME_001](frame.md#frame_001)

## STOP_016

After `StopHandle.cancel()` is called, that stop callback must not be called. A cancelled registration must be removed from the frame, and no reference to the callback must remain. This is so that registrations do not accumulate even when registration and cancellation are repeated inside a long-running frame (`Channel.get()` does this every time it waits). `cancel()` after the callback has already been called, or after the frame has ended, does nothing.

title: Cancelling a registration

level: MUST

## STOP_017

If a stop callback raises an exception, the exception must be recorded in `Frame.stop_errors`, and the frame must become a broken frame. The remaining stop callbacks of that frame continue to be called.

title: Errors in stop callbacks

level: MUST

related: [FRAME_001](frame.md#frame_001)

## STOP_018

A stop callback should finish quickly and should not keep blocking. A callback that does not return makes the frame a stuck frame by STOP_015.

title: Keeping callbacks short

level: SHOULD

condition: When writing a stop callback.

## STOP_019

`Session.stop()` must be callable regardless of the session's state, both before it is opened and after it is closed. If it is called before the session is opened, the session is in the stop-requested state at the time it is opened, and `spawn()` inside it returns stopped frames.

title: Stopping a session in any state

level: MUST

related: [SESSION_004](session.md#session_004), [FRAME_012](frame.md#frame_012)

## STOP_020

To stop a root session from a thread other than the one running `with` (signal handling, GUI events, other frames, and so on), create the session before `with`, pass a reference to it, and call its `stop()`. By STOP_019, the call is not missed even if it is made before entering `with` or during startup.

```python
app = gpframe.session(timeout=5)  # Create it in advance


def run() -> None:
    with app:
        app.spawn(worker)
        ...


# From another thread
app.stop()
```

title: Stopping a root session from another thread

level: INFORMATIVE
