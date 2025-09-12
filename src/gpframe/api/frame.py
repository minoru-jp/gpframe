from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from logging import Logger
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from ..impl.message import MessageReader, MessageUpdater

class Frame(ABC):
    __slots__ = ()
    @property
    @abstractmethod
    def frame_name(self) -> str:
        ...
    @property
    @abstractmethod
    def logger(self) -> Logger:
        ...
    @property
    @abstractmethod
    def routine_in_subprocess(self) -> bool:
        ...
    @property
    @abstractmethod
    def environment(self) -> MessageReader:
        ...
    @property
    @abstractmethod
    def request(self) -> MessageUpdater:
        ...
    @property
    @abstractmethod
    def event_message(self) -> MessageReader:
        ...
    @property
    @abstractmethod
    def routine_message(self) -> MessageReader:
        ...
    
    @abstractmethod
    def request_stop_routine(self, *, kill: bool = False) -> None:
        ...

    @abstractmethod
    def start(self, **options) -> asyncio.Task:
        ...

    @property
    @abstractmethod
    def task(self) -> asyncio.Task:
        ...
