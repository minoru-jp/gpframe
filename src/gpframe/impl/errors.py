
import asyncio

class HandledError(Exception):
    pass

class RoutineCancelledError(Exception):
    def __init__(self, original: asyncio.CancelledError):
        self.original = original

