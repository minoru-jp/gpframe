<!-- Published from devdocs/canonical_documents/specification/session.md sha256:df5fe1f8d032c492b1cc49ba1434e8ee73164be2c578b5697150fe3f0194b49c. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# Session

Rules on opening and closing sessions, spawning frames, judgement at exit, and sub-sessions.

## SESSION_001

A root session is created with `gpframe.session(timeout, strict)`, and a sub-session inside a frame is created with `Context.session(timeout)`. Both are used by opening them with `with`.

title: Creating sessions

level: INFORMATIVE

## SESSION_002

A session can be opened with `with` only once. An attempt to open it a second time must raise `SessionStateError`.

title: A session is entered once

level: MUST

## SESSION_003

`timeout` must be `None` or a number greater than or equal to 0. A negative number must be rejected with `ValueError` when the session is created.

title: Timeout values

level: MUST

## SESSION_004

`spawn()` can be used only on an open session.

- On a session before it is opened or after it is closed, it must raise `SessionStateError` without creating a frame. This is to avoid creating frames that escape the judgement at exit.
- On a session for which a stop has been requested, it must return a stopped frame without calling the routine (FRAME_012).

title: Spawning needs an open session

level: MUST

related: [FRAME_012](frame.md#frame_012)

## SESSION_005

`spawn(fn, *args, name=None)` must start a frame on a new daemon thread and call `fn(context, *args)` on that thread. Only positional arguments are passed to the routine.

title: Running a routine

level: MUST

## SESSION_006

If the result of calling the routine is a coroutine, a new event loop must be created in the frame's thread to run it to completion, and its result must be used as the return value of the routine.

title: Coroutine routines

level: MUST

## SESSION_007

If `name` is omitted, the frame's name is the routine's `__name__`, or, if it has none, the name of the routine's type. Names are for logs and reports, and they may be duplicated.

title: Frame names

level: MUST

## SESSION_008

`broken()` must return only the broken frames that are not yet acknowledged, in the order in which they were spawned. It must not include running frames, succeeded frames, or acknowledged frames.

title: Listing unacknowledged failures

level: MUST

related: [FRAME_001](frame.md#frame_001), [FRAME_008](frame.md#frame_008)

## SESSION_009

When exiting `with`, a session must proceed in the following order.

1. If an exception occurred inside the `with` block, request a stop.
2. Wait up to `timeout` seconds for all frames to end.
3. Move to the closed state, and treat frames that have not yet ended as stuck frames.
4. If there are stuck frames, request a stop.
5. For a root session, perform the judgement at exit; for a sub-session, report to the owner frame.

title: Exit procedure

level: MUST

## SESSION_010

If there are stuck frames, a root session must issue a `FrameWarning` that names them. The threads of stuck frames are not stopped; they keep running as they are.

title: Reporting stuck frames

level: MUST

## SESSION_011

A root session must handle the broken frames at exit according to their acknowledgement, as follows.

| Acknowledgement | Result |
| --- | --- |
| `ignore()` called | Do nothing |
| `escalate()` called | Include in `SessionFailed` and raise it |
| None (`strict=False`) | Issue a `FrameWarning` that names them |
| None (`strict=True`) | Include in `SessionFailed` and raise it |

An unacknowledged broken frame must not be discarded without either a warning or an exception.

title: Judgement at the root

level: MUST

related: [FRAME_008](frame.md#frame_008)

## SESSION_012

`SessionFailed` is an `ExceptionGroup`, and it must hold one exception for each frame that is included in it, in the order in which the frames were spawned. The `frames` attribute holds the corresponding frames in the same order. The exception for each frame is determined in the following order of priority.

1. If the routine ended with an `Exception`, that exception.
2. If the routine ended with a `BaseException` other than `Exception`, a `FrameAbortedError` that has it as its `__cause__`.
3. If a stop callback raised an exception, the first exception (wrapped as in 2. if it is not an `Exception`).
4. Otherwise (when a sub-session was incomplete), an `IncompleteSessionError` that holds the report.

The `reason` of `escalate(reason)` is included in the message together with the frame name.

title: Contents of SessionFailed

level: MUST

related: [FRAME_001](frame.md#frame_001), [FRAME_011](frame.md#frame_011)

## SESSION_013

When `SessionFailed` is divided with `split()` or `subgroup()`, the results must also be `SessionFailed`, and their `frames` must hold only the frames that correspond to the remaining exceptions.

title: Splitting SessionFailed

level: MUST

## SESSION_014

If an exception inside the `with` block coincides with raising `SessionFailed`, `SessionFailed` is raised, and the exception inside the block is kept as its `__context__`. If `SessionFailed` is not raised, the exception inside the block is re-raised as is.

title: Body errors and SessionFailed

level: MUST

## SESSION_015

A sub-session must not issue warnings and must not raise its own exceptions when exiting `with`. Only the root session makes the final decision.

title: Sub-sessions do not judge

level: MUST NOT

## SESSION_016

A sub-session is incomplete if any of the following applies, and it must attach its report (`SessionReport`) to the owner frame.

- There is a broken frame that has not been `ignore()`d (including ones that have been `escalate()`d)
- There is a stuck frame
- An exception occurred inside the `with` block

The report's `broken`, `stuck`, and `errors` correspond to the three items above, respectively.

title: Incomplete sub-sessions

level: MUST

related: [FRAME_002](frame.md#frame_002), [FRAME_007](frame.md#frame_007)

## SESSION_017

An exception that occurred inside the `with` block of a sub-session must be recorded in the report and then re-raised as is.

title: Body errors in sub-sessions

level: MUST

## SESSION_018

When an owner frame is `ignore()`d at the root, the failures that occurred under that frame are forgiven together with it. No means is provided to raise only the failures under it individually.

title: Ignoring a parent forgives its children

level: INFORMATIVE

## SESSION_019

A session must not hold frames that are no longer needed for the judgement at exit and the report. The following frames are released when they end (or, for ones that are `ignore()`d, when they are acknowledged).

- succeeded frames
- stopped frames
- broken frames that are `ignore()`d

Running frames, unacknowledged broken frames, and broken frames that are `escalate()`d are held for the judgement and the report. Released frames remain usable by whoever holds their handles.

This is so that ended frames do not keep accumulating in a session that stays open for a long time, such as a server that spawns a frame for each request.

title: A session keeps only what the judgement needs

level: MUST

related: [FRAME_001](frame.md#frame_001), [FRAME_013](frame.md#frame_013)
