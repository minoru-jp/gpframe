
from ..errors import HandledError

class FrameHandlerError(HandledError):
    def __init__(self, event_name: str, exc: Exception):
        super().__init__(f"{event_name} handler raises {type(exc).__name__}.")
        self.event_name = event_name
        self.cause = exc
