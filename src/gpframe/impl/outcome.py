from __future__ import annotations

from abc import ABC, abstractmethod
from types import MappingProxyType
from typing import Any

from ..api.outcome import Outcome

class OutcomeSource:
    __slots__ = (
        "_requests", "_event_messages", "_routine_messages",
        "_reader")
    def __init__(
            self,
            requests: dict,
            event_messages: dict,
            routine_messages: dict
        ):
        self._requests = MappingProxyType(requests)
        self._event_messages = MappingProxyType(event_messages)
        self._routine_messages = MappingProxyType(routine_messages)
        self._reader = self._create_reader()
    
    def _create_reader(self) -> Outcome:
        outer = self
        class _Interface(Outcome):
            __slots__ = ()
            @property
            def requests(self) -> MappingProxyType:
                return outer._requests
            @property
            def event_messages(self) -> MappingProxyType:
                return outer._event_messages
            @property
            def routine_messages(self) -> MappingProxyType:
                return outer._routine_messages
        return _Interface()
    
    @property
    def interface(self) -> Outcome:
        return self._reader

