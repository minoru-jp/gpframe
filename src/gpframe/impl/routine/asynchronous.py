
import asyncio
from logging import Logger
from threading import Lock, Thread
from typing import Any
from concurrent.futures import Future

from ...api.contexts import RoutineContext
from .result import NO_VALUE

from ..errors import HandledError

from .base import RoutineExecution
from .errors import CleanupTimeoutError, ExecutionError, RoutineTimeoutError

class FutureTimeoutError(RoutineTimeoutError):
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
    def __init__(self, future: Future, timeout: float):
        super().__init__(timeout)
        self.future = future

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
    __slots__ = ("_lock", "_loop", "_thread", "_future", "_called_stop")
    def __init__(self, frame_name: str, logger: Logger):
        try:
            self._lock = Lock()
            self._loop = asyncio.new_event_loop()
            self._thread = Thread(target = _worker, args = (self._loop,), daemon=True)
            self._thread.start()
            self._future = None
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
                self._future = asyncio.run_coroutine_threadsafe(routine(context), self._loop)
        except Exception as e:
            if isinstance(e, (HandledError, AssertionError)):
                raise
            else:
                raise ExecutionError(e) from e
    
    def wait_routine_result(self, frame_name: str, logger: Logger, timeout: float | None = None) -> tuple[Any | NO_VALUE, Exception | None]:
        try:
            if self._future is None:
                raise RuntimeError("routine is not loading")
            try:
                return self._future.result(timeout = timeout), None
            except asyncio.TimeoutError as e:
                assert timeout is not None
                raise FutureTimeoutError(self._future, timeout) from e
            except Exception as e:
                return NO_VALUE, e
            finally:
                with self._lock:
                    self._future = None
        except Exception as e:
            if isinstance(e, (HandledError, AssertionError)):
                raise
            else:
                raise ExecutionError(e) from e
    
    def routine_is_running(self) -> bool:
        try:
            with self._lock:
                return self._future.running() if self._future else False
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
                    if self._future and not self._future.cancelled():
                        self._future.cancel()
                else:
                    return
        except Exception as e:
            if isinstance(e, (HandledError, AssertionError)):
                raise
            raise ExecutionError(e)
    
    def cleanup(self, frame_name: str, logger: Logger, timeout: float | None = None) -> None:
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout = timeout)
            if self._thread.is_alive():
                assert timeout is not None
                raise ThreadCleanupTimeoutError(self._thread, timeout)
        except Exception as e:
            if isinstance(e, (HandledError, AssertionError)):
                raise
            raise ExecutionError(e) from e
        
    