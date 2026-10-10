<!-- Published from devdocs/canonical_documents/README.md sha256:d3c1a24fa8a9548ab8031d854234a4109a5b16d2578ddfa9c2e8f901b03aaf30. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# gpframe

`gpframe` is a small framework for building concurrent programs structurally, as a **tree of workers**.

You split a system into a few workers, and each worker has workers of its own below it. You can write that structure directly as code. At each level you only need to understand the workers directly below; without knowing what runs further down, you can reason about how the whole system stops and how it handles failures.

## Writing a tree of workers

For example, consider the following system.

```text
Application
├── WebServer
│   ├── RequestHandler
│   └── ConnectionManager
├── MessageWorker
│   ├── Consumer
│   └── Processor
└── Monitor
```

With gpframe, this tree becomes the code as it is.

```python
import gpframe


def supervise(s: gpframe.Session) -> None:
    """If any worker directly below fails, pass that failure up and stop its siblings."""
    for frame in s.wait_broken():
        frame.escalate()
    s.stop()


def idle(ctx: gpframe.Context) -> None:
    while not ctx.stopping:  # stands in for real work
        ctx.wait_stop(0.05)


def consumer(ctx: gpframe.Context) -> None:
    ctx.wait_stop(0.2)
    raise ConnectionError("broker unreachable")


def web_server(ctx: gpframe.Context) -> None:
    with ctx.session(timeout=5) as s:
        s.spawn(idle, name="RequestHandler")
        s.spawn(idle, name="ConnectionManager")
        supervise(s)


def message_worker(ctx: gpframe.Context) -> None:
    with ctx.session(timeout=5) as s:
        s.spawn(consumer, name="Consumer")
        s.spawn(idle, name="Processor")
        supervise(s)


try:
    with gpframe.session(timeout=5) as app:
        app.spawn(web_server, name="WebServer")
        app.spawn(message_worker, name="MessageWorker")
        app.spawn(idle, name="Monitor")
        supervise(app)
except gpframe.SessionFailed as failed:
    for frame in failed.frames:
        report = frame.incomplete
        causes = [f"{c.name}: {c.error}" for c in report.broken] if report else []
        print(frame.name, "failed because", ", ".join(causes))
```

When you run it, it prints `MessageWorker failed because Consumer: broker unreachable`, and the whole system stops.

What to notice when reading it is that every function **knows only the workers directly below it**. The root `app` starts only `WebServer`, `MessageWorker` and `Monitor`, and `message_worker` starts only `Consumer` and `Processor`. From the root, the failure of Consumer is seen as a single failure: "MessageWorker failed".

Every level is written in the same form, `supervise()`. In gpframe, each of these workers is called a **frame**, and the scope that holds frames together is called a **session**.

## Stop goes down, failures go up

You can reason at each level of the tree because stops and failures travel one level at a time, as follows.

- **A stop travels down.** `s.stop()` requests a stop of the frames directly below, and the request also reaches the sessions those frames have opened. A single `app.stop()` at the root stops the whole tree, and each worker only needs to know how to stop what is directly below it.
- **Failures travel up, gathered one level at a time.** A failure left unacknowledged in a session inside a worker becomes a failure of that worker itself. The parent sees only that one failure of the worker and does not need to know what is inside. If you want to know, you can follow it from `frame.incomplete`.
- **Expected failures are closed where they happen.** A failure that a worker `ignore()`s inside itself does not reach its parent. Each worker decides how much it takes on itself.
- **Only the root makes the final judgement.** In a session inside a frame, `escalate()` raises no exception; it only marks the failure and passes it to the parent. Whether to raise it as an exception or report it as a warning is decided by the root session.

You can build a tree of the asynchronous API (`gpframe.aio`) under a worker of the synchronous API. The reverse is not allowed: do not open a synchronous session under an asynchronous worker, because the waits of the synchronous API block the event loop.

## What to know first

- **Stopping is cooperative.** gpframe only requests a stop; whether the work actually stops depends on how it is written. Check `ctx.stopping` or `ctx.wait_stop()` in your work, or, for work that blocks, register how to stop it with `ctx.on_stop()`.
- **Threads that do not stop keep running.** Python threads cannot be stopped safely from outside. gpframe's responsibility ends at reporting such threads with a warning. Threads are started as daemon threads, so they do not prevent the process from exiting.
- **Work runs as threads or as asyncio tasks.** The synchronous `gpframe` runs frames as threads, and the asynchronous `gpframe.aio` runs them as tasks on an event loop. Parallel execution in processes is not covered. Threads are for running waits (I/O or stops) side by side; splitting Python computation across several threads does not make it faster.
- Python `>=3.11` is required.

## Installation

```bash
pip install "gpframe>=0.1.0"
```

The `0.0.x` releases on PyPI are the old implementation from before the rewrite and are not compatible with this README.

## Tools for keeping the structure

From here on, the tools gpframe provides for keeping the structure of the tree are explained one by one. Acknowledging failures and the stopping mechanism are not goals in themselves; they exist to make the boundaries between workers clear.

### Writing one level

Inside a session opened with `gpframe.session()`, each function you `spawn()` runs as one thread (a frame). The function receives a `Context` as its first argument, and the remaining arguments are the ones passed to `spawn()`, as they are.

```python
import gpframe


def parse(ctx: gpframe.Context, text: str) -> int:
    return int(text)


with gpframe.session(timeout=5) as s:
    frames = [s.spawn(parse, text) for text in ["1", "2", "x"]]
    s.wait()
    for frame in s.broken():
        if isinstance(frame.error, ValueError):
            frame.ignore()  # acknowledge it as an expected failure
        else:
            frame.escalate()  # unexpected; becomes SessionFailed when leaving the with block

print(sum(f.result() for f in frames if f.succeeded))  # 3
```

The `Frame` returned by `spawn()` is a handle close to `concurrent.futures.Future`, and `result()` gives the return value. A routine may also be an `async def`. If you open `ctx.session()` inside a frame, you can build another level below that frame.

### Acknowledging failures

A frame that ended with an exception becomes a **broken frame**. `s.broken()` returns only broken frames that have not been acknowledged yet, so calling it repeatedly while polling never handles the same frame twice.

When leaving the `with` block of the root session, the remaining broken frames are handled as follows.

| State | Result when leaving `with` |
| --- | --- |
| All `ignore()`d, or no failures | Nothing happens |
| Some were `escalate()`d | Raises `SessionFailed` (an `ExceptionGroup`) |
| Some have neither mark | Warns with `FrameWarning` |
| Some have no mark, with `strict=True` | Includes them in the raised `SessionFailed` |

`SessionFailed` is an `ExceptionGroup`, so you can receive it per exception type with `except*`. Calling `f.result()` and looking at the exception does not acknowledge it. Whether to accept a failure is always made explicit with `ignore()` or `escalate()`.

A failure `escalate()`d in a sub-session does not become an exception on the spot. It is attached to the owner frame as the sub-session's report, and appears one level up as a failure of that frame **when the owner frame's routine returns**. Inside a frame that keeps running for a long time, such as a monitoring loop, the failure does not surface until it returns, so if you want to pass it up right away, raise an exception on the spot.

```python
for frame in sub.wait_broken():
    raise ConnectionError(frame.name) from frame.error  # make this frame fail right now
```

### Stopping

`s.stop()` requests a stop of every frame in the session. If a routine uses `ctx.stopping` as its loop condition and `ctx.wait_stop()` instead of `time.sleep()`, it can respond to the request immediately.

```python
import time

import gpframe


def ticker(ctx: gpframe.Context, interval: float) -> int:
    count = 0
    while not ctx.stopping:
        count += 1
        ctx.wait_stop(interval)  # a sleep that wakes up as soon as a stop is requested
    return count


with gpframe.session(timeout=5) as s:
    frame = s.spawn(ticker, 0.1)
    time.sleep(0.5)
    s.stop()

print(frame.result() > 0)  # True
```

When leaving `with`, the session waits up to `timeout` seconds (until they finish, with the default `None`) for its frames to end. Frames that did not stop in time are reported with `FrameWarning` as **stuck frames**; the session requests a stop and moves on. If an exception occurs inside the `with` block, the session requests a stop before waiting.

A frame `spawn()`ed after a stop is returned as a **stopped** frame without calling its routine (`frame.stopped` is `True`). Work that was about to start while things were stopping is not a failure, so it is neither an exception nor something to acknowledge. Even if a stop arrives between checking for a stop and spawning, you do not need to write anything extra. However, the routine is not called, so if you passed something that needs cleanup as an argument, such as an accepted socket, check `frame.stopped` and close it yourself.

To stop the root session from a signal handler or another thread, create the session before `with`, pass a reference to it around, and call its `stop()`. `stop()` can be called even before entering `with`; in that case the session is already stopped when it is opened.

### Stopping components that block

A component that keeps blocking inside, such as an HTTP server, cannot check `ctx.stopping`. For such components, combine two tools.

- `ctx.on_stop(callback)` registers a function to call when a stop is requested. For `serve_forever()`, register `server.shutdown` to tell gpframe how to stop it. The callback is called once, in another thread, and `stop()` does not wait for it to finish.
- `s.wait_broken()` waits until the first failure appears and returns `broken()` at that moment. If everything ends without a failure, or the wait times out, it returns an empty sequence.

```python
import http.server

import gpframe


def web(ctx: gpframe.Context) -> None:
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), http.server.BaseHTTPRequestHandler
    )
    ctx.on_stop(server.shutdown)  # stop the blocking serve_forever()
    with server:
        server.serve_forever()


def worker(ctx: gpframe.Context) -> None:
    ctx.wait_stop(0.2)
    raise RuntimeError("worker crashed")


try:
    with gpframe.session(timeout=5) as s:
        s.spawn(web)
        s.spawn(worker)
        for frame in s.wait_broken():  # wait for the first failure
            frame.escalate("component failed")
        s.stop()  # stop the remaining components too
except* RuntimeError as group:
    print(group.exceptions[0])  # worker crashed
```

If a stop callback raises an exception, that frame also becomes a broken frame, and the exception can be read from `Frame.stop_errors`.

When collecting the results of frames run in parallel, check for failures with `wait_broken()` before `[f.result() for f in frames]`. If you wait on `result()` in the order the frames were started, you will not notice a frame that failed early until the slow frames ahead of it have finished.

To wait only for the end of one frame, however it ends, such as "stop the writer when the reader ends", use `frame.wait()`. It raises no exception and returns `True` once the frame has ended.

In a server that spawns a frame for each connection or request, keep waiting for failures with `wait_broken(idle=True)`. It does not return even when no frame is running; it returns on a failure or a stop request. The session lets go of frames that have ended (including those that were `ignore()`d), so they do not pile up even when it runs for a long time.

```python
while not ctx.stopping:
    for frame in clients.wait_broken(idle=True):
        log.info("%s failed: %r", frame.name, frame.error)
        frame.ignore()  # failures of single connections are settled at this level
```

### Sharing values

To share a value between frames, use `Shared`. You decide its type and initial value when creating it, and the value always stays of that type. `apply()` performs everything from reading to writing as one operation, so concurrent updates are not lost.

```python
import gpframe


def work(ctx: gpframe.Context, done: gpframe.Shared[int]) -> None:
    for _ in range(1_000):
        done.apply(lambda n: n + 1)  # read and write as one operation


done = gpframe.Shared(int, 0)  # decide the type and the initial value together
with gpframe.session() as s:
    for _ in range(4):
        s.spawn(work, done)

print(done.get())  # 4000
```

To keep several values consistent together, put an immutable dataclass in one `Shared` and replace it as a whole with `apply()`. To receive results, use the return values of frames.

### Passing values

To pass values in order from one frame to another, use `Channel`. On the receiving side, `receive(ctx)` waits for values to arrive and **leaves the loop naturally when a stop is requested**. Without writing a separate way to stop, you get a worker that can be stopped.

```python
import gpframe


def produce(ctx: gpframe.Context, jobs: gpframe.Channel[int]) -> None:
    for n in range(1, 11):
        jobs.put(n)
    jobs.close()  # tell the receivers nothing more will be sent


def consume(ctx: gpframe.Context, jobs: gpframe.Channel[int]) -> int:
    # leave the loop when a stop is requested, or when the channel is closed and empty
    return sum(n * n for n in jobs.receive(ctx))


jobs = gpframe.Channel(int)
with gpframe.session(timeout=5) as s:
    s.spawn(produce, jobs)
    consumers = [s.spawn(consume, jobs) for _ in range(3)]  # the three share the values
    for frame in s.wait_broken():
        frame.escalate()

print(sum(f.result() for f in consumers))  # 385
```

- `put(item)` returns without waiting and can also be called from threads outside frames.
- `close()` is the notice "nothing more will be sent". The remaining values are delivered, and the receiving loops end once the channel is empty.
- After a stop is requested, values are not received even if some remain. This keeps new work from starting after a stop.
- To take values one at a time, use `get(ctx, timeout)`. It returns `None` when there is no value, and the reason can be told apart with `ctx.stopping` and `jobs.closed`.

If the sender is faster than the receiver, values keep piling up in the channel. Give it a limit, as in `Channel(Job, maxsize=100)`, and use `put(item, ctx)` on the sending side. When the channel is full, it waits until there is space; a stop request or `close()` ends the wait and it returns `False`. `put(item)` without `ctx` raises `ChannelFullError` without waiting when the channel is full. There is no way to silently drop values when the channel is full.

```python
for batch in read_batches():
    if not lines.put(batch, ctx):  # wait until there is space if full
        return  # stopped, or the downstream closed
```

In the log aggregation example, without a limit almost the whole 44MB log piled up in the channel (112MB); with a limit of 20 it took 24MB, at the same speed.

When passing large numbers of small values, pass them gathered in lists (annotate `Channel(list)` as `gpframe.Channel[list[str]]`). Passed one at a time, the cost of handing them over between threads becomes larger than the processing itself. In the log aggregation example (`examples/logstats.py`), just gathering 500 lines at a time made it about four times faster.

`Channel` is a component of the synchronous API only. In the asynchronous API a stop is a cancellation, so a wait on `asyncio.Queue` is stopped by it as it is.

## The asynchronous API (gpframe.aio)

`gpframe.aio` is the asynchronous API, which runs frames as tasks on an event loop. It is an independent API that shares no types with the synchronous API; you open it with `async with`, and every wait is done with `await`. A tree of workers is written in the same form in the asynchronous API too (open the level below with `ctx.session()`).

- **A stop is a cancellation.** `s.stop()` cancels the tasks of the frames, and a frame that ended because of a stop request is not a failure but stopped. A frame that ended by a cancellation gpframe did not request is broken.
- **Only coroutine functions can be passed to `spawn()`.** Calling a synchronous function on the loop could block the loop.
- **Routines that do not use `ctx` are common.** A stop arrives as a cancellation. You can avoid type checkers' warnings about unused arguments by naming it `_ctx`.
- **The health check `aio.monitor()` watches for stalls of the loop.** A thread outside the loop measures how late the loop responds, and when it detects a stall, it reports it together with the stack of the place that is blocking.

```python
import asyncio

from gpframe import aio


async def web(ctx: aio.AsyncContext) -> None:
    await asyncio.Event().wait()  # runs on; a stop arrives as a cancellation


async def worker(ctx: aio.AsyncContext) -> None:
    await asyncio.sleep(0.1)
    raise RuntimeError("worker crashed")


async def main() -> None:
    async with aio.monitor():  # report stalls of the loop longer than 1 second
        async with aio.session(timeout=5) as s:
            s.spawn(web)
            s.spawn(worker)
            for frame in await s.wait_broken():  # wait for the first failure
                frame.escalate("component failed")
            s.stop()  # stop the remaining components by cancellation


try:
    asyncio.run(main())
except* RuntimeError as group:
    print(group.exceptions[0])  # worker crashed
```

The asynchronous API has inherent limitations that come from running on a single loop. If a frame blocks the loop, the guarantees of `timeout` and of reporting are lost. A task that ignores cancellation is reported as not having stopped and is then detached, and its cleanup is not guaranteed. For details, see "Constraints and limits" in the Specification of the asynchronous API.

## Development

The tools needed for development are gathered in the `dev` extra. Every check is run with `tools/check.py`, and CI and releases use the same one.

```console
pip install -e ".[dev]"
python tools/check.py            # every check
python tools/check.py lint tests # only the chosen checks
```

Rules of behavior are written in the canonical sources (in Japanese) under `devdocs/canonical_sources/`, and `python scripts/render_devdocs.py` generates the canonical documents. The English published documents are translations of the canonical documents.

## Related documents

- [STATUS.md](https://github.com/minoru-jp/gpframe/blob/main/STATUS.md): development stage, scope, state of quality, and future direction
- [docs/specification/INDEX.md](https://github.com/minoru-jp/gpframe/blob/main/docs/specification/INDEX.md): rules of behavior (Specification)
- [docs/specification_aio/INDEX.md](https://github.com/minoru-jp/gpframe/blob/main/docs/specification_aio/INDEX.md): rules of behavior of the asynchronous API, with its constraints and limitations
- [CHANGELOG.md](https://github.com/minoru-jp/gpframe/blob/main/CHANGELOG.md): changes in each version
