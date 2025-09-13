from __future__ import annotations

import sys

from logging import Logger
from threading import Lock
from typing import Any, Literal, cast

from multiprocessing import Queue, Manager, Process
from queue import Empty

from logging.handlers import QueueListener

from ...api.contexts import RoutineContext

from ..errors import HandledError
from .result import NO_VALUE

from .base import RoutineExecution, SyncWaitFn, AsyncWaitFn
from .errors import ExecutionError, RoutineTimeoutError


class SubprocessTimeoutError(RoutineTimeoutError):
    """
    Raised when a subprocess does not finish execution within the given timeout.

    This exception is a specialized form of RoutineTimeoutError. The
    `process` attribute stores the Process instance that did not
    terminate in time.

    Attributes
    ----------
    process : Process
        The subprocess that exceeded the timeout.
    timeout : float
        The timeout value in seconds.
    """
    def __init__(self, process: Process, timeout: float):
        super().__init__(timeout)
        self.process = process


class SubprocessError(Exception):
    def __init__(self, exitcode: int | None):
        super().__init__(f"Subprocess execution failed (exit code {exitcode})")
        self.exitcode = exitcode
    

def _subprocess_entry(routine, context: RoutineContext, result_queue: Queue, log_queue: Queue):
    import logging, logging.handlers

    logger = logging.getLogger(context.logger_name)
    logger.addHandler(logging.handlers.QueueHandler(log_queue))

    try:
        result = routine(context), None
    except Exception as e:
        result = NO_VALUE, e

    result_queue.put(result)

    sys.exit(0)

class SyncRoutineInSubprocess(RoutineExecution):
    __slots__ = ("_lock", "_sync_manager", "_result_queue", "_log_queue", "_listener", "_process", "_called_stop")
    def __init__(self, frame_name: str, logger: Logger, options: dict):
        try:
            self._sync_manager = Manager()
            self._lock = self._sync_manager.Lock()
            self._result_queue = Queue()
            self._log_queue = Queue()
            self._listener = QueueListener(self._log_queue, *logger.handlers)
            self._listener.start()
            self._process = None
            self._called_stop = False
        except Exception as e:
            if isinstance(e, (HandledError, AssertionError)):
                raise
            else:
                raise ExecutionError(e) from e
    
    def get_shared_lock(self) -> Lock:
        return self._lock
    
    def get_shared_map_factory(self) -> type[dict]:
        return cast(type[dict], self._sync_manager.dict)
    
    def load_routine(self, frame_name, logger: Logger, routine, context: RoutineContext) -> None:
        try:
            with self._lock:
                self._called_stop = False
                self._process = Process(
                    target = _subprocess_entry,
                    args = (routine, context, self._result_queue, self._log_queue)
                )
            self._process.start()
        except Exception as e:
            if isinstance(e, (HandledError, AssertionError)):
                raise
            else:
                raise ExecutionError(e) from e
    
    def wait_routine_result(self, frame_name: str, logger: Logger, timeout: float | None = None) -> tuple[Any | NO_VALUE, Exception | None]:
        try: 
            if self._process is None:
                raise RuntimeError("routine is not loading")
            try:
                self._process.join(timeout = timeout)
                if not self._process.is_alive():
                    exitcode = self._process.exitcode
                    if exitcode == 0:
                        return self._result_queue.get_nowait()
                    else:
                        raise SubprocessError(exitcode)
                else:
                    assert timeout is not None
                    raise SubprocessTimeoutError(self._process, timeout) 
            finally:
                while True:
                    try:
                        self._result_queue.get_nowait()
                    except Empty:
                        break
                with self._lock:
                    self._process = None
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
                return self._process.is_alive() if self._process else False
        except Exception as e:
            if isinstance(e, (HandledError, AssertionError)):
                raise
            else:
                raise ExecutionError(e) from e
    
    def request_stop_routine(self, frame_name: str, logger: Logger, **kwargs) -> None:
        try:
            with self._lock:
                if not self._called_stop:
                    self._called_stop = True
                    if self._process is not None:
                        if kwargs.get("kill", False):
                            self._process.kill()
                        else:
                            self._process.terminate()
                else:
                    return
        except Exception as e:
            if isinstance(e, (HandledError, AssertionError)):
                raise
            else:
                raise ExecutionError(e) from e
    
    def cleanup(self, frame_name: str, logger: Logger, timeout: float | None = None) -> None:
        try:
            self._result_queue.close()
            self._result_queue.join_thread()
            self._listener.enqueue_sentinel()
            self._listener.stop()
            self._log_queue.close()
            self._log_queue.join_thread()
            self._sync_manager.shutdown()
        except Exception as e:
            if isinstance(e, (HandledError, AssertionError)):
                raise
            else:
                raise ExecutionError(e) from e
    