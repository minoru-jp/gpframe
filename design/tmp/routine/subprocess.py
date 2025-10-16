from __future__ import annotations

import asyncio
import inspect
import sys

from logging import Logger
from threading import Lock
from typing import Any

from multiprocessing import Queue, Process
from queue import Empty

from logging.handlers import QueueListener

from gpframe.contracts.api import gproot, gpsub
from gpframe.contracts.exceptions import RoutineSubprocessTimeoutError

from gpframe._impl.routine.base import (
    _NO_VALUE,
    IPCRoutineExecution,
    SyncRoutineResultWaitFn,
    AsyncRoutineResultWaitFn
)

from gpframe._impl.protocols import _QueueLike

class SubprocessError(Exception):
    def __init__(self, exitcode: int | None):
        super().__init__(f"Subprocess execution failed (exit code {exitcode})")
        self.exitcode = exitcode
    

def _subprocess_entry(routine, context: gproot.ipc.routine.Context | gpsub.ipc.routine.Context, result_queue: Queue, log_queue: Queue):
    import logging, logging.handlers

    logger = logging.getLogger(context.logger_name)
    logger.addHandler(logging.handlers.QueueHandler(log_queue))

    try:
        if inspect.iscoroutinefunction(routine):
            result = asyncio.run(routine(context)), None
        else:
            result = routine(context), None
    except Exception as e:
        result = _NO_VALUE, e

    result_queue.put(result)

    sys.exit(0)

class SyncRoutineInSubprocess(IPCRoutineExecution):
    __slots__ = ("_lock", "_result_queue", "_log_queue", "_listener", "_process", "_called_stop")
    def __init__(self, lock: Lock, r_queue: _QueueLike, l_queue: _QueueLike):
        self._lock = lock
        self._result_queue = r_queue
        self._log_queue = l_queue
        self._process = None
        self._called_stop = False
    
    def set_logger_unsafe(self, logger: Logger):
        self._listener = QueueListener(self._log_queue, *logger.handlers)
        self._listener.start()
    
    def load_routine(self, routine, context) -> None:
        with self._lock:
            self._called_stop = False
            self._process = Process(
                target = _subprocess_entry,
                args = (routine, context, self._result_queue, self._log_queue)
            )
        self._process.start()
    
    def wait_routine_result(self, timeout: float | None = None) -> tuple[Any | _NO_VALUE, Exception | None]:
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
                raise RoutineSubprocessTimeoutError(self._process, timeout) 
        finally:
            while True:
                try:
                    self._result_queue.get_nowait()
                except Empty:
                    break
            with self._lock:
                self._process = None
    
    def get_wait_routine_result_fn(self) -> SyncRoutineResultWaitFn | AsyncRoutineResultWaitFn:
        return self.wait_routine_result
    
    def routine_is_running(self) -> bool:
        with self._lock:
            return self._process.is_alive() if self._process else False
    
    def request_stop_routine(self, kill: bool) -> None:
        with self._lock:
            if not self._called_stop:
                self._called_stop = True
                if self._process is not None:
                    if kill:
                        self._process.kill()
                    else:
                        self._process.terminate()
            else:
                return
    
    def cleanup(self, timeout: float | None = None) -> None:
        self._listener.enqueue_sentinel()
        self._listener.stop()
    