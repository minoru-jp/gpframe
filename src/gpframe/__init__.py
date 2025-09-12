"""
gpframe: A general-purpose framework for routine execution with concurrency and event handling.
------------

Note
---------------
This library is in an early stage of development.
It is generally unstable: documentation and tests are incomplete,
and the API may undergo breaking changes without notice.


Core Components
---------------
- FrameBuilder (from .api.builder):
  Factory function to obtain a FrameBuilderType.  
  Accepts a routine to be executed inside a Frame.  
  The routine can be synchronous or asynchronous.

- FrameBuilderType (from .api.builder):
  API to configure the Frame name, logger, and handlers.  
  Calling FrameBuilderType.start() launches the Frame and returns a Frame object.

- Frame (from .api.frame):
  Represents the entire lifecycle of a Frame.  
  Provides Frame.task for accessing the Frame's execution task.  
  Allows writing to the request message map via Frame.request.update().

- EventContext (from .api.contexts):
  Allows writing to the event_message map through EventContext.event_message.update().

- RoutineContext (from .api.contexts):
  Allows writing to the routine_message map through RoutineContext.routine_message.update().

- Outcome (from .api.outcome):
  Passed to the on_terminated handler after the Frame has finished (after on_close).  
  Provides read-only access to all message maps.  
  Each message map is a snapshot of its state at termination.


Message Updaters / Readers
--------------------------
gpframe defines four synchronized message registries and one result container.  
These registries are the core mechanism for communication between the Frame, the routine, and event handlers.  
Each registry is exposed as a MessageReader (read-only) or MessageUpdater (read-write), depending on context.

1. environment
   - Purpose: Immutable configuration or contextual information.
   - Access:
       Read: Frame, EventContext, RoutineContext
       Write: Frame (setup stage only)
   - Example: constants, system configuration, resource identifiers.

2. request
   - Purpose: Incoming requests or instructions that affect routine behavior.
   - Access:
       Read: Frame, EventContext, RoutineContext
       Write: Frame (via Frame.request.update())
   - Example: runtime parameters, control flags.

3. event_message
   - Purpose: Event-driven updates produced by event handlers.
   - Access:
       Read: Frame, RoutineContext
       Write: EventContext (via EventContext.event_message.update())
   - Example: status events, log signals, external notifications.

4. routine_message
   - Purpose: Communication channel from the routine to other components.
   - Access:
       Read: Frame, EventContext
       Write: RoutineContext (via RoutineContext.routine_message.update())
   - Example: progress reports, intermediate results.

5. routine_result
   - Purpose: Result value of the routine execution.
   - Access:
       Read: EventContext.routine_result
       Write: set internally by each routine execution
   - Behavior:
       Updated every time the routine finishes (success, error, or cancellation).
       After the Frame terminates, the last value represents the final outcome.
   - Special values:
       NO_VALUE = not yet executed, canceled, interrupted, or failed.

MessageReader API
-----------------
A read-only view of a registry.

- geta(key, default=...) -> Any  
  Retrieve a value by key without type checking.  
  If missing and no default given, raises KeyError.

- getd(key, typ: type[T], default: D) -> T | D  
  Retrieve a value by key and validate its type.  
  If missing, return the given default (which may have a different type).

- get(key, typ: type[T]) -> T  
  Retrieve a value by key and validate its type.  
  Raises KeyError if missing, TypeError if mismatched.


MessageUpdater API
------------------
A read-write view of a registry.

- geta(key, default=...) -> Any  
  Retrieve a value by key without type checking.  
  If missing and no default given, raises KeyError.

- getd(key, typ: type[T], default: D) -> T | D  
  Retrieve a value by key and validate its type.  
  If missing, return the given default (which may have a different type).

- get(key, typ: type[T]) -> T  
  Retrieve a value by key and validate its type.  
  Raises KeyError if missing, TypeError if mismatched.

- update(key, value) -> T  
  Store a value under the given key, returning it.

- apply(key, typ: type[T], fn: Callable[[T], T], default=...) -> T  
  Atomically update a value using a function.  
  If missing, the default value is used (must be compatible with `typ`):

      ctx.event_message.apply("count", int, lambda c: c + 1, default=0)

- remove(key, default=None) -> Any  
  Remove a key and return its value.  
  If absent, return the given default.


String Conversion Utilities
---------------------------
Both `MessageReader` and `MessageUpdater` provide the following helpers to
convert string values stored in the registry.

Common Behavior

- If the key does not exist and no default is provided, a `KeyError` is raised.  
- If a default value is provided and its type already matches the *converted* type of the method
  (e.g., `int` for `string_to_int`, `float` for `string_to_float`, `bool` for `string_to_bool`, `str` for `string`),  
  then the default is returned directly without going through `prep` or `valid`.  
- Otherwise, the stored value (or the default) is first converted to `str` and processed.

- `prep` may be given as either a single callable `(str -> str)` or a tuple of such callables.  
  If a tuple is provided, each function is applied in order to the string before conversion.  
- After conversion, the resulting value is passed to `valid` (if applicable).  
  If `valid` returns `False`, a `ValueError` is raised.

Methods

- string(key, default=..., *, prep=..., valid=...) -> str  
  Retrieve the value by key, convert it with `str(...)`, and return it.  
  This acts as a string-typed getter regardless of the stored type.  
  The string may be preprocessed by `prep` and must satisfy `valid`.

- string_to_int(key, default=..., *, prep=..., valid=...) -> int  
  Retrieve a string by key and convert it to an integer.  
  Supports standard prefixes (0x, 0o, 0b) via `int(string, 0)`.  
  Preprocessing and validation are applied as described above.

- string_to_float(key, default=..., *, prep=..., valid=...) -> float  
  Retrieve a string by key and convert it to a float.  
  Preprocessing and validation are applied as described above.

- string_to_bool(key, default=..., *, prep=..., true=(), false=()) -> bool  
  Retrieve a string by key and convert it to a boolean.  
  Preprocessing is applied as described above.  
  If neither `true` nor `false` sets are provided, non-empty strings evaluate to `True`.  
  If only `true` is given, returns `True` if the string matches, `False` otherwise.  
  If only `false` is given, returns `False` if the string matches, `True` otherwise.  
  If both are given, raises `ValueError` if the string does not match either.


       
Lifecycle and Access Rules
--------------------------
- All maps are thread-safe (backed by SynchronizedMapReader/SynchronizedMapUpdater).
- During Frame execution, access is restricted according to context type.
- After Frame termination, direct access is invalid and raises TerminatedError.
  To inspect final state, use Outcome which contains a snapshot of all maps.

  
Lifecycle Overview
------------------

1. on_open
   - Called first at the very beginning.

2. on_start
   - Called before routine execution.

3. routine
   - The main processing logic.

4. on_end
   - Called immediately after routine finishes.

5. on_redo
   - Called right after on_end.
   - If it returns True, the loop continues with on_start → routine → on_end → on_redo.
   - If it returns False, the loop breaks and termination begins.

6. on_cancel  (shielded)
   - Called when asyncio.CancelledError is raised.

7. on_close  (shielded)
   - Always called at the end, regardless of success, failure, or cancellation.

8. on_terminated  (shielded)
   - Always called after on_close.


Control Flow (Summary)
----------------------
on_open
→ (loop) [ on_start → routine → on_end → on_redo ]
    ├─ on_redo == True → loop continues
    └─ on_redo == False → loop ends
→ finally: on_close → on_terminated

※ If asyncio.CancelledError is raised during execution,
   on_cancel will be called first, then finally on_close → on_terminated.

   
Error Handling
--------------
- If an exception occurs in any handler (on_* / routine / on_redo),
  it is passed to exception_handler.

  - exception_handler is shielded.

- If exception_handler returns False, the exception is re-raised (propagates upward).

- Regardless of exceptions, on_close and on_terminated are always executed.

- NO_VALUE (from .impl.routine.result):
  Initial value of EventContext.routine_result.value.  
  Indicates that no routine result exists (not yet executed, exception raised, etc.).

- TerminatedError (from .impl.builder):
  Raised when attempting to access message maps after a Frame has terminated.  
  In such cases, maps must be accessed via Outcome.

- FutureTimeoutError, ThreadCleanupTimeoutError (from .impl.routine.asynchronous):
  Timeout-related errors for asynchronous routines and thread cleanup.

- SubprocessTimeoutError (from .impl.routine.subprocess):
  Timeout error for subprocess routines.

- Throw (from .impl.handler.exception):
  Exception wrapper for re-throwing errors without being wrapped as HandlerError.  
  Useful when propagating exceptions such as asyncio.CancelledError directly.

"""

from .api.builder import FrameBuilder

from .api.builder import FrameBuilderType

from .api.frame import Frame

from .api.contexts import EventContext
from .api.contexts import RoutineContext

from .api.outcome import Outcome

from .impl.routine.result import NO_VALUE

from .impl.builder import TerminatedError

from .impl.routine.asynchronous import TaskTimeoutError, ThreadCleanupTimeoutError
from .impl.routine.subprocess import SubprocessTimeoutError

from .impl.handler.exception import Throw

__all__ = ("FrameBuilder", "FrameBuilderType",
           "Frame",
           "EventContext", "RoutineContext",
           "Outcome",
           "NO_VALUE",
           "TerminatedError", 
           "TaskTimeoutError", "ThreadCleanupTimeoutError",
           "SubprocessTimeoutError",
           "Throw")
