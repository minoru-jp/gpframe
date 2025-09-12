from __future__ import annotations

import asyncio
from logging import Logger
from threading import Lock, Thread
from typing import Any
from concurrent.futures import Future

from gpframe.impl.routine.base import AsyncWaitFn, SyncWaitFn

from ...api.contexts import RoutineContext
from .result import NO_VALUE

from ..errors import HandledError

from .base import RoutineExecution, AsyncWaitFn, SyncWaitFn
from .errors import CleanupTimeoutError, ExecutionError, RoutineTimeoutError

class TaskTimeoutError(RoutineTimeoutError):
    """
    Raised when a Future does not complete within the given timeout.

    This exception is a specialized form of RoutineTimeoutError. The
    `future` attribute stores the Future instance that failed to finish
    in time.

    Attributes
    ----------
    future : Future
        The future that exceeded the timeout.
    """
    def __init__(self, task: asyncio.Task, timeout: float):
        super().__init__(timeout)
        self.future = task

class ThreadCleanupTimeoutError(CleanupTimeoutError):
    """
    Raised when a thread does not finish during cleanup within the given timeout.

    This exception is a specialized form of CleanupTimeoutError. The
    `thread` attribute stores the Thread instance that failed to
    terminate in time.

    Attributes
    ----------
    thread : Thread
        The thread that exceeded the cleanup timeout.
    """
    def __init__(self, thread: Thread, timeout: float):
        super().__init__(timeout)
        self.thread = thread

def _worker(loop: asyncio.AbstractEventLoop):
    asyncio.set_event_loop(loop)
    try:
        loop.run_forever()
    finally:
        loop.close()

class AsyncRoutine(RoutineExecution):
    __slots__ = ("_lock", "_loop", "_task", "_called_stop")
    def __init__(self, frame_name: str, logger: Logger, options: dict, share: RoutineExecution | None = None):
        try:
            if share and not isinstance(share, AsyncRoutine):
                raise TypeError
            self._lock = Lock() if not share else share.get_shared_lock()
            loop = options["loop"] if "loop" in options else asyncio.get_running_loop()
            if not isinstance(loop, asyncio.AbstractEventLoop):
                raise TypeError
            self._loop = loop
            self._task = None
            self._called_stop = False
        except Exception as e:
            if isinstance(e, (HandledError, AssertionError)):
                raise
            else:
                raise ExecutionError(e) from e
        
    
    def get_shared_lock(self) -> Lock:
        try:
            return self._lock
        except Exception as e:
            if isinstance(e, (HandledError, AssertionError)):
                raise
            else:
                raise ExecutionError(e) from e
        
    
    def get_shared_map_factory(self) -> type[dict]:
        return dict
    
    def load_routine(self, frame_name: str, logger: Logger, routine, context: RoutineContext) -> None:
        try:
            with self._lock:
                self._called_stop = False
                self._task = asyncio.create_task(routine(context))
        except Exception as e:
            if isinstance(e, (HandledError, AssertionError)):
                raise
            else:
                raise ExecutionError(e) from e
    
    async def wait_routine_result(self, frame_name: str, logger: Logger, timeout: float | None = None) -> tuple[Any | NO_VALUE, Exception | None]:
        try:
            if self._task is None:
                raise RuntimeError("routine is not loading")
            try:
                return await asyncio.wait_for(self._task, timeout), None
            except asyncio.TimeoutError as e:
                raise TaskTimeoutError(self._task, timeout if timeout is not None else -1.0) from e
            except Exception as e:
                return NO_VALUE, e
            finally:
                with self._lock:
                    self._task = None
        except Exception as e:
            if isinstance(e, (HandledError, AssertionError)):
                raise
            else:
                raise ExecutionError(e) from e
    
    def get_wait_routine_result_fn(self) -> SyncWaitFn | AsyncWaitFn:
        return self.wait_routine_result
    
    def routine_is_running(self) -> bool:
        try:
            with self._lock:
                return not self._task.done() if self._task else False
        except Exception as e:
            if isinstance(e, (HandledError, AssertionError)):
                raise
            raise ExecutionError(e) from e
    
    def request_stop_routine(self, frame_name: str, logger: Logger, **kwargs) -> None:
        try:
            assert self._lock
            with self._lock:
                if not self._called_stop:
                    self._called_stop = True
                    if self._task and not self._task.cancelled():
                        self._task.cancel()
                else:
                    return
        except Exception as e:
            if isinstance(e, (HandledError, AssertionError)):
                raise
            raise ExecutionError(e)
    
    def cleanup(self, frame_name: str, logger: Logger, timeout: float | None = None) -> None:
        pass
        


# import asyncio
# from logging import Logger
# from threading import Lock, Thread
# from typing import Any
# from concurrent.futures import Future

# from ...api.contexts import RoutineContext
# from .result import NO_VALUE

# from ..errors import HandledError

# from .base import RoutineExecution
# from .errors import CleanupTimeoutError, ExecutionError, RoutineTimeoutError

# class FutureTimeoutError(RoutineTimeoutError):
#     """
#     Raised when a Future does not complete within the given timeout.

#     This exception is a specialized form of RoutineTimeoutError. The
#     `future` attribute stores the Future instance that failed to finish
#     in time.

#     Attributes
#     ----------
#     future : Future
#         The future that exceeded the timeout.
#     """
#     def __init__(self, future: Future, timeout: float):
#         super().__init__(timeout)
#         self.future = future

# class ThreadCleanupTimeoutError(CleanupTimeoutError):
#     """
#     Raised when a thread does not finish during cleanup within the given timeout.

#     This exception is a specialized form of CleanupTimeoutError. The
#     `thread` attribute stores the Thread instance that failed to
#     terminate in time.

#     Attributes
#     ----------
#     thread : Thread
#         The thread that exceeded the cleanup timeout.
#     """
#     def __init__(self, thread: Thread, timeout: float):
#         super().__init__(timeout)
#         self.thread = thread

# def _worker(loop: asyncio.AbstractEventLoop):
#     asyncio.set_event_loop(loop)
#     try:
#         loop.run_forever()
#     finally:
#         loop.close()

# class AsyncRoutine(RoutineExecution):
#     __slots__ = ("_lock", "_loop", "_thread", "_future", "_called_stop")
#     def __init__(self, frame_name: str, logger: Logger, options: dict):
#         try:
#             self._lock = Lock()
#             self._loop = asyncio.new_event_loop()
#             self._thread = Thread(target = _worker, args = (self._loop,), daemon=True)
#             self._thread.start()
#             self._future = None
#             self._called_stop = False
#         except Exception as e:
#             if isinstance(e, (HandledError, AssertionError)):
#                 raise
#             else:
#                 raise ExecutionError(e) from e
        
    
#     def get_shared_lock(self) -> Lock:
#         try:
#             return self._lock
#         except Exception as e:
#             if isinstance(e, (HandledError, AssertionError)):
#                 raise
#             else:
#                 raise ExecutionError(e) from e
        
    
#     def get_shared_map_factory(self) -> type[dict]:
#         return dict
    
#     def load_routine(self, frame_name: str, logger: Logger, routine, context: RoutineContext) -> None:
#         try:
#             with self._lock:
#                 self._called_stop = False
#                 self._future = asyncio.run_coroutine_threadsafe(routine(context), self._loop)
#         except Exception as e:
#             if isinstance(e, (HandledError, AssertionError)):
#                 raise
#             else:
#                 raise ExecutionError(e) from e
    
#     def wait_routine_result(self, frame_name: str, logger: Logger, timeout: float | None = None) -> tuple[Any | NO_VALUE, Exception | None]:
#         try:
#             if self._future is None:
#                 raise RuntimeError("routine is not loading")
#             try:
#                 return self._future.result(timeout = timeout), None
#             except asyncio.TimeoutError as e:
#                 assert timeout is not None
#                 raise FutureTimeoutError(self._future, timeout) from e
#             except Exception as e:
#                 return NO_VALUE, e
#             finally:
#                 with self._lock:
#                     self._future = None
#         except Exception as e:
#             if isinstance(e, (HandledError, AssertionError)):
#                 raise
#             else:
#                 raise ExecutionError(e) from e
    
#     def routine_is_running(self) -> bool:
#         try:
#             with self._lock:
#                 return self._future.running() if self._future else False
#         except Exception as e:
#             if isinstance(e, (HandledError, AssertionError)):
#                 raise
#             raise ExecutionError(e) from e
    
#     def request_stop_routine(self, frame_name: str, logger: Logger, **kwargs) -> None:
#         try:
#             assert self._lock
#             with self._lock:
#                 if not self._called_stop:
#                     self._called_stop = True
#                     if self._future and not self._future.cancelled():
#                         self._future.cancel()
#                 else:
#                     return
#         except Exception as e:
#             if isinstance(e, (HandledError, AssertionError)):
#                 raise
#             raise ExecutionError(e)
    
#     def cleanup(self, frame_name: str, logger: Logger, timeout: float | None = None) -> None:
#         try:
#             self._loop.call_soon_threadsafe(self._loop.stop)
#             self._thread.join(timeout = timeout)
#             if self._thread.is_alive():
#                 assert timeout is not None
#                 raise ThreadCleanupTimeoutError(self._thread, timeout)
#         except Exception as e:
#             if isinstance(e, (HandledError, AssertionError)):
#                 raise
#             raise ExecutionError(e) from e
        
    