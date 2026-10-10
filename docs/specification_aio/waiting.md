<!-- Published from devdocs/canonical_documents/specification_aio/waiting.md sha256:2efcbb5f2261eee38ed2383ed4e12c891e62e96ce6d90ca176b2257d7438d516. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# Async waiting

Rules on how, in the asynchronous API, to wait for all frames to end and for the first failure without stopping the event loop.

## AWAIT_001

`AsyncSession.running()` is not a coroutine, and it returns `True` if there are frames that have not yet ended.

title: Running frames

level: MUST

## AWAIT_002

`await AsyncSession.wait(timeout)` waits up to `timeout` seconds for all frames to end, without stopping the event loop, and returns `True` if all of them end in time, or `False` otherwise. It also waits for frames spawned while it is waiting to end.

title: Waiting for all frames

level: MUST

## AWAIT_003

`await AsyncSession.wait_broken(timeout, *, idle=False)` must wait up to `timeout` seconds, without stopping the event loop, until any of the following holds. If one already holds at the time of the call, it returns immediately.

- There is a broken frame that is not yet acknowledged
- There are no running frames (when `idle=False`. For `idle=True`, see AWAIT_008)
- `timeout` seconds have elapsed

title: Waiting for the first failure

level: MUST

related: [AFRAME_003](frame.md#aframe_003)

## AWAIT_004

`wait_broken()` returns the same sequence as `broken()` at the time it returns. An empty result means that it returned for a reason other than a failure, and `running()` can distinguish which reason it was. Stopped frames are not treated as failures.

title: Result of wait_broken

level: MUST

related: [ASESSION_009](session.md#asession_009)

## AWAIT_005

Frames returned by `wait_broken()` must not be treated as acknowledged.

title: Waiting does not acknowledge

level: MUST NOT

related: [AFRAME_011](frame.md#aframe_011)

## AWAIT_006

If a task waiting in `wait()` or `wait_broken()` is cancelled, the wait ends with that `asyncio.CancelledError`. The frames must not be cancelled or stopped.

title: Cancelling a waiter does not stop frames

level: MUST NOT

related: [AFRAME_007](frame.md#aframe_007)

## AWAIT_007

Processing that connects long-running components and stops the whole when any one of them fails can be written in the following form. Unlike the synchronous API, the stop arrives at each component's await points as a cancellation.

```python
async with gpframe.aio.session(timeout=10) as s:
    for component in components:
        s.spawn(component)
    if failed := await s.wait_broken():
        for frame in failed:
            frame.escalate()
        s.stop()
```

title: Supervising long-running components

level: INFORMATIVE

## AWAIT_008

`await wait_broken(idle=True)` must not return because there are no running frames. It must wait until there is a broken frame that is not yet acknowledged, a stop has been requested from the session, or `timeout` seconds have elapsed. Same as WAIT_007 of the synchronous API.

title: Waiting while idle

level: MUST

## AWAIT_009

A server that spawns a frame for each connection keeps waiting for failures with `idle=True`, and settles the failures at the accepting level. A stop arrives at this wait as a cancellation.

```python
while True:
    for frame in await clients.wait_broken(idle=True):
        log(frame)
        frame.ignore()
```

title: Supervising a changing set of frames

level: INFORMATIVE
