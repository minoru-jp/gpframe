<!-- Published from devdocs/canonical_documents/specification/waiting.md sha256:101049e811cdbea1a9a9b8bda8be45a44b87bc694f85878609b4d55b1b0b95f7. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# Waiting

Rules on how to wait for all frames to end and how to wait for the first failure.

## WAIT_001

`Session.running()` must return `True` if there are frames that have not yet ended.

title: Running frames

level: MUST

## WAIT_002

`Session.wait(timeout)` must wait up to `timeout` seconds for all frames to end, and return `True` if all of them end in time, and `False` otherwise. It also waits for frames spawned while it is waiting to end. If `timeout` is `None`, it waits until all of them end.

title: Waiting for all frames

level: MUST

## WAIT_003

`Session.wait_broken(timeout, *, idle=False)` must wait up to `timeout` seconds until any of the following holds.

- There is a broken frame that is not yet acknowledged
- There are no running frames (when `idle=False`; for `idle=True`, see WAIT_007)
- `timeout` seconds have passed

If one already holds at the time of the call, it returns immediately. If `timeout` is `None`, it does not time out.

title: Waiting for the first failure

level: MUST

related: [FRAME_001](frame.md#frame_001)

## WAIT_004

`wait_broken()` must return the same sequence as `broken()` at the time it returns. A non-empty result means it returned because of a failure; an empty result means it returned because of the end of the frames or a timeout. These two can be distinguished with `running()` (WAIT_001).

title: Result of wait_broken

level: MUST

related: [SESSION_008](session.md#session_008)

## WAIT_005

Frames returned by `wait_broken()` must not be treated as acknowledged. A subsequent call to `wait_broken()` keeps returning the same frames until they are acknowledged.

title: Waiting does not acknowledge

level: MUST NOT

related: [FRAME_005](frame.md#frame_005)

## WAIT_006

Processing that connects long-running components and stops everything when any one of them fails can be written in the following form.

```python
with gpframe.session(timeout=10) as s:
    for component in components:
        s.spawn(component)
    if failed := s.wait_broken():
        for frame in failed:
            frame.escalate()
        s.stop()
```

To restart only the failed components, call `wait_broken()` repeatedly, acknowledge the failures, and then `spawn()` the same routines again.

title: Supervising long-running components

level: INFORMATIVE

## WAIT_007

`wait_broken(idle=True)` does not return because there are no running frames, and must wait until any of the following holds.

- There is a broken frame that is not yet acknowledged
- A stop has been requested for the session
- `timeout` seconds have passed

Because it returns on a stop request, a loop that keeps waiting can be exited by a stop. As in WAIT_004, the return value is `broken()` at the time it returns.

title: Waiting while idle

level: MUST

## WAIT_008

When frames come and go in a session, such as in a server that spawns a frame for each connection or request, keep waiting for failures with `idle=True`, and settle the failures at that one level. This is the same form as a `selectors` loop.

```python
while not ctx.stopping:
    for frame in clients.wait_broken(idle=True):
        log(frame)
        frame.ignore()
```

title: Supervising a changing set of frames

level: INFORMATIVE
