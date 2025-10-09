
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

class FrameAggregateError(Exception):
    def __init__(
        self,
        root_name: str,
        root_error: BaseException | None,
        sub_errors: dict[str, BaseException],
    ):
        self.root_frame_name = root_name
        self.root_frame_error = root_error
        self.sub_frame_errors = sub_errors

        # Build message
        parts: list[str] = []
        if root_error is not None:
            # Root error always comes first
            parts.append(f"{root_name}: {type(root_error).__name__}")
        # Then add subframe errors
        for name, exc in sub_errors.items():
            parts.append(f"{name}: {type(exc).__name__}")

        msg = (
            f"The root frame '{root_name}' has terminated with errors.\n"
            f"The following frames raised errors:\n  "
            + ", ".join(parts)
        )

        super().__init__(msg)

class FrameAlreadyStartedError(Exception):
    pass

