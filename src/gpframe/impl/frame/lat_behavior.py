from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, auto
from threading import Lock
from typing import Any, Callable, Protocol, TypeVar

R = TypeVar("R")

def _noop():
    pass

class StateError(Exception):
    pass

class LATStateError(StateError):
    pass

class LATState(IntEnum):
    LOAD = 0
    STARTED = auto()
    TERMINATED = auto()

    def get_next(self) -> LATState | None:
        try:
            return LATState(self.value + 1)
        except ValueError:
            return None
    
    def transitionable(self, to: LATState):
        return self.get_next() is to

class LATBehavior(Protocol):

    def on_load(self, fn: Callable[[], R] = _noop) -> R:
        ...
    
    def if_load(self, fn: Callable[[], R]) -> R:
        ...

    def to_active(self, fn: Callable[[], R] = _noop) -> R:
        ...

    def on_active(self, fn: Callable[[], R] = _noop) -> R:
        ...
    
    def if_active(self, fn: Callable[[], R]) -> R:
        ...
    
    def to_terminated(self, fn: Callable[[], R] = _noop) -> R:
        ...
    
    def on_terminated(self, fn: Callable[[], R] = _noop) -> R:
        ...

    def if_terminated(self, fn: Callable[[], R]) -> R:
        ...
    
    def on_any(self, fn: Callable[[], R]) -> R:
        ...





# @dataclass(slots = True)
# class _State:
#     lock: Lock
#     current_phase: LATState


# class _Core:
#     __slots__ = ()
#     def initialzie(self) -> _State:
#         return _State(Lock(), LATState.LOAD)
    
#     def maintain(self, state: _State, keep: LATState, fn: Callable[[], R]) -> R:
#         with state.lock:
#             if keep is state.current_phase:
#                 return fn()
#             else:
#                 raise StateError
    
#     def if_on(self, state: _State, on: LATState, fn: Callable[[], Any]):
#         with state.lock:
#             if on is state.current_phase:
#                 return fn()

#     def transit_state_unsafe(self, state: _State, to: LATState) -> None:
#         current_phase = state.current_phase
#         if not current_phase.transitionable(to):
#             raise StateError(f"Invalid transition: {current_phase} → {to}")
#         state.current_phase = to

#     def transit_state_with(self, state: _State, to: LATState, fn: Callable[[], R]) -> R:
#         with state.lock:
#             self.transit_state_unsafe(state, to)
#             return fn()

#     def transit_state(self, state: _State, to: LATState) -> None:
#         with state.lock:
#             self.transit_state_unsafe(state, to)
    
#     def on_any(self, state: _State, fn: Callable[[], R]) -> R:
#         # No state check is performed here, only mutual exclusion (locking) is applied.
#         with state.lock:
#             return fn()

# @dataclass(slots = True)
# class _Role:
#     state: _State
#     core: _Core
#     interface: LATBehavior



# def create_phase_manager_role():

#     core = _Core()

#     state = core.initialzie()

#     class _Interface(LATBehavior):
#         def on_load(self, fn: Callable[[], R] = _noop) -> R:
#             return core.maintain(state, LATState.LOAD, fn)

#         def to_started(self, fn: Callable[[], R] = _noop) -> R:
#             return core.transit_state_with(state, LATState.STARTED, fn)

#         def on_started(self, fn: Callable[[], R] = _noop) -> R:
#             return core.maintain(state, LATState.STARTED, fn)

#         def to_terminated(self, fn: Callable[[], R] = _noop) -> R:
#             return core.transit_state_with(state, LATState.TERMINATED, fn)

#         def on_terminated(self, fn: Callable[[], R] = _noop) -> R:
#             return core.maintain(state, LATState.TERMINATED, fn)
    
#         def if_terminated(self, fn: Callable[[], R] = _noop) -> None:
#             core.if_on(state, LATState.TERMINATED, fn)
        
#         def on_any(self, fn: Callable[[], R] = _noop) -> R:
#             return core.on_any(state, fn)


#     interface = _Interface()
    
#     return _Role(
#         state = state,
#         core = core,
#         interface = interface
#     )
