<!-- Published from devdocs/canonical_documents/specification/channel.md sha256:d01a6030f82051ea67e7c7a01e8a98178ab79768792dc6d05ce691a289d10d74. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# Channel

Rules on `Channel`, which passes values between frames in order and whose send and receive waits are released by a stop request.

## CHANNEL_001

`Channel` is a component for passing values between frames in first-in, first-out order. The receiving side waits until a value arrives, a stop is requested, or the channel is closed. If a limit is placed on the capacity, the adding side also waits until space becomes available. Both waits are released by a stop, so simply writing a send or receive loop makes a worker that can be stopped.

```python
jobs = gpframe.Channel(Job, maxsize=100)


def producer(ctx: gpframe.Context, jobs: gpframe.Channel[Job]) -> None:
    for job in source():
        if not jobs.put(job, ctx):  # If full, wait until there is space. False on stop
            return
    jobs.close()


def consumer(ctx: gpframe.Context, jobs: gpframe.Channel[Job]) -> None:
    for job in jobs.receive(ctx):  # Ends on stop, or when closed and empty
        handle(job)
```

title: Purpose

level: INFORMATIVE

## CHANNEL_002

The `typ` of `Channel(typ, maxsize=0)` must be a runtime class that can be checked with `isinstance()`, and must not be `NoneType`. If this is not satisfied, `DeclaredTypeError` is raised. The declared type can be read with `Channel.type`.

title: Declared type

level: MUST

related: [SHARED_001](shared.md#shared_001)

## CHANNEL_016

`maxsize` must be an integer greater than or equal to 0, and a negative number is rejected with `ValueError` at creation. 0 means no limit. If it is a positive number, the number of values held by the channel must not exceed `maxsize`. The configured value can be read with `Channel.maxsize`.

title: Capacity

level: MUST

## CHANNEL_003

The `item` of `put(item, ctx=None, timeout=None)` must be an instance of the declared type that is not `None`. If this is not satisfied, `DeclaredTypeError` is raised and nothing is added. Because `None` cannot be put in, a `None` on receipt means only that there is no value.

title: Putting values

level: MUST

related: [SHARED_002](shared.md#shared_002)

## CHANNEL_004

`put(item)` without `ctx` must return without waiting. It can also be called from threads outside frames. Since there is nothing to check in the return value, it returns `None` (only `put()` with `ctx` returns a `bool`).

| State | Result |
| --- | --- |
| There is space (always, if there is no limit) | Add to the end (the return value is `None`) |
| Full | Raise `ChannelFullError` without adding anything |
| Closed | Raise `ChannelClosedError` without adding anything (CHANNEL_005) |

title: Putting without a context never waits

level: MUST

## CHANNEL_005

`put()` without `ctx` must raise `ChannelClosedError` on a closed channel without adding anything. `put()` with `ctx` returns `False` without adding anything if the channel is closed (CHANNEL_017).

title: Putting after close

level: MUST

## CHANNEL_017

`put(item, ctx, timeout=None)` with `ctx` adds the item to the end and returns `True` if there is space. If the channel is full, it must wait up to `timeout` seconds until any of the following occurs. If `timeout` is `None`, it waits without limit.

| What occurred | Result |
| --- | --- |
| Space became available | Add to the end and return `True` |
| A stop was requested for the session of `ctx` | Return `False` without adding anything |
| The channel was closed | Return `False` without adding anything |
| `timeout` seconds passed | Return `False` without adding anything |

If a stop has been requested or the channel is closed at the time of the call, it also returns `False` without adding anything, regardless of space. This is so that no new work flows after a stop, and so that the result for the same condition does not depend on the time of the call. Releasing the wait on a stop happens without being missed and leaves no registration behind, the same as `get()` in CHANNEL_010. `timeout` must be `None` or a number greater than or equal to 0, and a negative number is rejected with `ValueError`.

title: Putting with a context waits for space

level: MUST

related: [STOP_011](stop.md#stop_011), [STOP_016](stop.md#stop_016)

## CHANNEL_018

The reason `put()` returned `False` can be distinguished with `ctx.stopping` and `Channel.closed`. If it is neither, it was a timeout.

title: Telling why put() returned False

level: INFORMATIVE

## CHANNEL_006

Values must be taken out in the order in which they were added. Each value is received by only one receiver. When multiple frames receive from the same channel, the values are shared out among them.

title: Order and delivery

level: MUST

## CHANNEL_007

`get(ctx, timeout=None)` takes out and returns the next value. If the channel is empty, it must wait up to `timeout` seconds until any of the following occurs. If `timeout` is `None`, it waits without limit.

| What occurred | Result |
| --- | --- |
| A value was added | Return that value |
| A stop was requested for the session of `ctx` | Return `None` |
| The channel was closed | Return `None` |
| `timeout` seconds passed | Return `None` |

`timeout` must be `None` or a number greater than or equal to 0, and a negative number is rejected with `ValueError`.

title: Getting a value

level: MUST

## CHANNEL_008

While a stop is requested for the session of `ctx`, `get()` must return `None` without taking out a value, even if values remain in the channel. This is so that no new work starts after a stop. Values that were not taken out remain in the channel.

title: Stop takes precedence over values

level: MUST

related: [STOP_002](stop.md#stop_002)

## CHANNEL_009

While values remain in a closed channel, `get()` must return those values. Closing is a notice that "nothing more will be added", and values already added reach the receivers. `get()` returns `None` when the channel is closed and has also become empty.

title: Close lets remaining values through

level: MUST

## CHANNEL_010

Releasing the wait of `get()` on a stop must happen without being missed, in the same way as for stop callbacks, regardless of the path through which the stop is requested (`stop()`, propagation from the parent, or a request by the session itself). After `get()` returns, no registration made for that purpose must remain.

title: Waking on a stop request

level: MUST

related: [STOP_011](stop.md#stop_011), [STOP_012](stop.md#stop_012)

## CHANNEL_011

`receive(ctx)` must be an iterator that yields the values in order while `get(ctx)` returns values, and ends when it returns `None`.

title: Receiving in a loop

level: MUST

## CHANNEL_012

The reason `get()` returned `None` can be distinguished with `ctx.stopping` and `Channel.closed`. If it is neither, it was a timeout.

title: Telling why get() returned None

level: INFORMATIVE

## CHANNEL_013

`close()` must close the channel and wake all waiting `get()` calls. Calling it two or more times results in the same state as calling it once. No means is provided to reopen a closed channel. `closed` returns `True` if the channel is closed.

title: Closing

level: MUST

## CHANNEL_014

A `Context` other than that of the frame making the call must not be passed to `get()`, `receive()`, or `put()`. The wait is released by a stop of the session of the passed `Context`, so with the `Context` of another frame, the calling frame may become impossible to stop.

title: Which context to pass

level: MUST NOT

condition: When calling `get()`, `receive()`, or `put()` with `ctx`.

## CHANNEL_015

The following are not provided.

- Handling that discards old or new values when the channel is full. To avoid silently losing values, a full channel is expressed either by waiting (with `ctx`) or by an exception (without `ctx`).
- A means to wait on multiple channels at the same time (select).
- An asynchronous version of `Channel`. In the asynchronous case, a stop is a cancellation, so a wait on `asyncio.Queue` is stopped by the cancellation as it is. Calling `get()` of `Channel` on the loop blocks the loop.

title: What Channel does not provide

level: INFORMATIVE
