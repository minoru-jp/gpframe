from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum, auto
from threading import Lock
from typing import Any, Callable, TypeVar

R = TypeVar("R")

def _NOOP():
    pass

class PhaseManager(ABC):
    __slots__ = ()

    @abstractmethod
    def on_load(self, fn: Callable[[], R] = _NOOP) -> R:
        ...

    @abstractmethod
    def to_started(self, fn: Callable[[], R] = _NOOP) -> R:
        ...

    @abstractmethod
    def on_started(self, fn: Callable[[], R] = _NOOP) -> R:
        ...
    
    @abstractmethod
    def to_terminated(self, fn: Callable[[], R] = _NOOP) -> R:
        ...
    
    @abstractmethod
    def on_terminated(self, fn: Callable[[], R] = _NOOP) -> R:
        ...

    def if_terminated(self, fn: Callable[[], R] = _NOOP) -> None:
        ...
    
    def on_any(self, fn: Callable[[], R] = _NOOP) -> R:
        ...

class Phase(IntEnum):
    LOAD = 0
    STARTED = auto()
    TERMINATED = auto()

    def get_next(self):
        return Phase(self.value + 1)
    
    def transitionable(self, to: Phase):
        return self.get_next() is to

class InvalidPhaseError(Exception):
    pass

@dataclass(slots = True)
class _State:
    lock: Lock
    current_phase: Phase


class _Core:
    __slots__ = ()
    def initialzie(self) -> _State:
        return _State(Lock(), Phase.LOAD)
    
    def maintain(self, state: _State, keep: Phase, fn: Callable[[], R]) -> R:
        with state.lock:
            if keep is state.current_phase:
                return fn()
            else:
                raise InvalidPhaseError
    
    def if_on(self, state: _State, on: Phase, fn: Callable[[], Any]):
        with state.lock:
            if on is state.current_phase:
                return fn()

    def transit_state_unsafe(self, state: _State, to: Phase) -> None:
        current_phase = state.current_phase
        if not current_phase.transitionable(to):
            raise InvalidPhaseError(f"Invalid transition: {current_phase} → {to}")
        state.current_phase = to

    def transit_state_with(self, state: _State, to: Phase, fn: Callable[[], R]) -> R:
        with state.lock:
            self.transit_state_unsafe(state, to)
            return fn()

    def transit_state(self, state: _State, to: Phase) -> None:
        with state.lock:
            self.transit_state_unsafe(state, to)
    
    def on_any(self, state: _State, fn: Callable[[], R]) -> R:
        # No state check is performed here, only mutual exclusion (locking) is applied.
        with state.lock:
            return fn()

@dataclass(slots = True)
class _Role:
    state: _State
    core: _Core
    interface: PhaseManager



def create_phase_manager_role():

    core = _Core()

    state = core.initialzie()

    class _Interface(PhaseManager):
        def on_load(self, fn: Callable[[], R] = _NOOP) -> R:
            return core.maintain(state, Phase.LOAD, fn)

        def to_started(self, fn: Callable[[], R] = _NOOP) -> R:
            return core.transit_state_with(state, Phase.STARTED, fn)

        def on_started(self, fn: Callable[[], R] = _NOOP) -> R:
            return core.maintain(state, Phase.STARTED, fn)

        def to_terminated(self, fn: Callable[[], R] = _NOOP) -> R:
            return core.transit_state_with(state, Phase.TERMINATED, fn)

        def on_terminated(self, fn: Callable[[], R] = _NOOP) -> R:
            return core.maintain(state, Phase.TERMINATED, fn)
    
        def if_terminated(self, fn: Callable[[], R] = _NOOP) -> None:
            core.if_on(state, Phase.TERMINATED, fn)
        
        def on_any(self, fn: Callable[[], R] = _NOOP) -> R:
            return core.on_any(state, fn)


    interface = _Interface()
    
    return _Role(
        state = state,
        core = core,
        interface = interface
    )
