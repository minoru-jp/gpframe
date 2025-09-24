
import asyncio
from multiprocessing import Process


class HandledTimeoutError(Exception):
    pass

class RoutineTimeoutError(HandledTimeoutError):
    def __init__(self, timeout: float):
        super().__init__(f"routine did not finish within {timeout} seconds")

class CleanupTimeoutError(HandledTimeoutError):
    def __init__(self, timeout: float):
        super().__init__(f"cleanup did not finish within {timeout} seconds")


class RoutineSubprocessTimeoutError(RoutineTimeoutError):
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

class RoutineTaskTimeoutError(RoutineTimeoutError):
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


class FrameTerminatedError(Exception):
    pass

class RoutineResultTypeError(TypeError):
    pass

class RoutineResultMissingError(Exception):
    pass

class FrameFutureAggregateError(Exception):
    def __init__(self, errors: dict[str, BaseException]):
        if not errors:
            raise ValueError(
                "FrameFutureAggregateError must not be "
                "created with an empty errors dict."
            )
        self.errors = errors
        first_item = next(iter(errors.items()))
        first_name, first_exc = first_item
        super().__init__(
            f"Multiple frame futures raised exceptions. "
            f"First error from '{first_name}': {first_exc!r}. "
            f"See .errors for the complete list."
        )
    
    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.errors:
            frames = ", ".join(self.errors.keys())
            return f"{base_msg} (frames with errors: {frames})"
        return base_msg

class FrameAlreadyStartedError(Exception):
    pass

