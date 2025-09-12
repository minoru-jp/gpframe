from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import MappingProxyType

class Outcome(ABC):
    __slots__ = ()
    @property
    @abstractmethod
    def requests(self) -> MappingProxyType:
        ...
    @property
    @abstractmethod
    def event_messages(self) -> MappingProxyType:
        ...
    @property
    @abstractmethod
    def routine_messages(self) -> MappingProxyType:
        ...

