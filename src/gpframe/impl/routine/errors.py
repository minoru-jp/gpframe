
from ..errors import HandledError

class ExecutionError(Exception):
    def __init__(self, e):
        super().__init__(repr(e))

class HandledTimeoutError(HandledError):
    pass

class RoutineTimeoutError(HandledTimeoutError):
    def __init__(self, timeout: float):
        super().__init__(f"routine did not finish within {timeout} seconds")

class CleanupTimeoutError(HandledTimeoutError):
    def __init__(self, timeout: float):
        super().__init__(f"cleanup did not finish within {timeout} seconds")


