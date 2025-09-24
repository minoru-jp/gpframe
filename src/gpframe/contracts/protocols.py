from __future__ import annotations

import logging

from typing import Protocol, Any, Awaitable, Callable, Union, ContextManager

from gpframe._impl.common import _T, _K, _D, _NO_DEFAULT, _noop, _any_str, _any_int, _any_float

class message:
    class MessageReader(Protocol[_K]):
        def geta(self, key: _K, default: Any = _NO_DEFAULT) -> Any:
            ...
        def getd(self, key: _K, typ: type[_T], default: _D) -> _T | _D:
            ...
        def get(self, key: _K, typ: type[_T]) -> _T:
            ...
        def string(
            self,
            key: _K,
            default: Any = _NO_DEFAULT,
            *,
            prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
            valid: Callable[[str], bool] = _any_str,
        ) -> str:
            ...
        def string_to_int(
            self,
            key: _K,
            default: int | Any = _NO_DEFAULT,
            *,
            prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
            valid: Callable[[int], bool] = _any_int,
        ) -> int:
            ...
        def string_to_float(
            self,
            key: _K,
            default: float | Any = _NO_DEFAULT,
            *,
            prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
            valid: Callable[[float], bool] = _any_float,
        ) -> float:
            ...
        def string_to_bool(
            self,
            key: _K,
            default: bool | Any = _NO_DEFAULT,
            *,
            prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
            true: tuple[str, ...] = (),
            false: tuple[str, ...] = (),
        ) -> bool:
            ...


    class MessageUpdater(MessageReader[_K], Protocol[_K]):
        def update(self, key: _K, value: _T) -> _T:
            ...
        def apply(self, key: _K, typ: type[_T], fn: Callable[[_T], _T], default: _T | type[_NO_DEFAULT] = _NO_DEFAULT) -> _T:
            ...
        def remove(self, key: _K, default: Any = None) -> Any:
            ...

class _IntraProcessContext(Protocol):
    @property
    def frame_name(self) -> str:
        ...
    @property
    def logger(self) -> logging.Logger:
        ...
    @property
    def environment(self) -> message.MessageReader[Any]:
        ...
    @property
    def routine_result(self) -> routine.Result:
        ...
    @property
    def inter_frame(self) -> message.MessageUpdater[str]:
        ...
    @property
    def ipc(self) -> message.MessageUpdater[str]:
        ...

class _IPCContext(Protocol):
    @property
    def frame_name(self) -> str:
        ...
    @property
    def logger_name(self) -> str:
        ...
    @property
    def ipc(self) -> message.MessageUpdater[str]:
        ...

# class param:
#     class root:
#         class Context(_IntraProcessContext, Protocol):
#             __slots__ = ()
#             @property
#             def request(self) -> message.MessageUpdater[Any]:
#                 ...
#             @property
#             def event_message(self) -> message.MessageReader[Any]:
#                 ...
#             @property
#             def routine_message(self) -> message.MessageUpdater[Any]:
#                 ...
#             def start_sub_frame(self, frame_name: str) -> FrameFuture:
#                 ...

#         class ipc:
#             class Context(_IPCContext, Protocol):
#                 pass
    
#     class sub:
#         class Context(_IntraProcessContext, Protocol):
#             @property
#             def request(self) -> message.MessageReader[Any]:
#                 ...
#             @property
#             def event_message(self) -> message.MessageReader[Any]:
#                 ...
#             @property
#             def routine_message(self) -> message.MessageUpdater[Any]:
#                 ...

#         class ipc:
#             class Context(_IPCContext, Protocol):
#                 pass

#     class event:
#         class root:
#             class Context(_IntraProcessContext, Protocol):
#                 @property
#                 def request(self) -> message.MessageReader[Any]:
#                     ...
#                 @property
#                 def event_message(self) -> message.MessageUpdater[Any]:
#                     ...
#                 @property
#                 def routine_message(self) -> message.MessageReader[Any]:
#                     ...
#                 def start_sub_frame(self, frame_name: str) -> FrameFuture:
#                     ...
        
#         class sub:
#             class Context(_IntraProcessContext, Protocol):
#                 @property
#                 def request(self) -> message.MessageReader[Any]:
#                     ...
#                 @property
#                 def event_message(self) -> message.MessageUpdater[Any]:
#                     ...
#                 @property
#                 def routine_message(self) -> message.MessageReader[Any]:
#                     ...
        
class gproot:
    class routine:
        class Context(_IntraProcessContext, Protocol):
            __slots__ = ()
            @property
            def request(self) -> message.MessageUpdater[Any]:
                ...
            @property
            def event_message(self) -> message.MessageReader[Any]:
                ...
            @property
            def routine_message(self) -> message.MessageUpdater[Any]:
                ...
            def start_sub_frame(self, frame_name: str) -> FrameFuture:
                ...
    class event:
        class Context(_IntraProcessContext, Protocol):
            @property
            def request(self) -> message.MessageReader[Any]:
                ...
            @property
            def event_message(self) -> message.MessageUpdater[Any]:
                ...
            @property
            def routine_message(self) -> message.MessageReader[Any]:
                ...
            def start_sub_frame(self, frame_name: str) -> FrameFuture:
                ...
    class ipc:
        class routine:
            class Context(_IPCContext, Protocol):
                pass
        class event:
            class Context(_IntraProcessContext, Protocol):
                @property
                def request(self) -> message.MessageReader[Any]:
                    ...
                @property
                def event_message(self) -> message.MessageUpdater[Any]:
                    ...
                @property
                def routine_message(self) -> message.MessageReader[Any]:
                    ...
                def start_sub_frame(self, frame_name: str) -> FrameFuture:
                    ...

class gpsub:
    class routine:
        class Context(_IntraProcessContext, Protocol):
            @property
            def request(self) -> message.MessageReader[Any]:
                ...
            @property
            def event_message(self) -> message.MessageReader[Any]:
                ...
            @property
            def routine_message(self) -> message.MessageUpdater[Any]:
                ...
    class event:
        class Context(_IntraProcessContext, Protocol):
            @property
            def request(self) -> message.MessageReader[Any]:
                ...
            @property
            def event_message(self) -> message.MessageUpdater[Any]:
                ...
            @property
            def routine_message(self) -> message.MessageReader[Any]:
                ...
    class ipc:
        class routine:
            class Context(_IPCContext, Protocol):
                pass
        class event:
            class Context(_IntraProcessContext, Protocol):
                @property
                def request(self) -> message.MessageReader[Any]:
                    ...
                @property
                def event_message(self) -> message.MessageUpdater[Any]:
                    ...
                @property
                def routine_message(self) -> message.MessageReader[Any]:
                    ...

class routine:

    Root = Callable[[gproot.routine.Context], Any] | Callable[[gproot.routine.Context], Awaitable[Any]]
    Sub = Callable[[gpsub.routine.Context], Any] | Callable[[gpsub.routine.Context], Awaitable[Any]]

    class Result(Protocol):
        def get(self, typ: type[_T]) -> _T:
            ...
        
        def getd(self, typ: type[_T], default: _D = _NO_DEFAULT) -> _T | _D:
            ...

        def geta(self, default: Any = _NO_DEFAULT) -> Any:
            ...

        @property
        def error(self) -> Exception | None:
            ...
    
    class ipc:
        Root = Callable[[gproot.ipc.routine.Context], Any] | Callable[[gproot.ipc.routine.Context], Awaitable[Any]]
        Sub = Callable[[gpsub.ipc.routine.Context], Any] | Callable[[gproot.ipc.routine.Context], Awaitable[Any]]


class handler:
    class root:
        EventHandler = Union[
            Callable[[gproot.event.Context], None],
            Callable[[gproot.event.Context], Awaitable[None]],
        ]

        ExceptionHandler = Union[
            Callable[[gproot.event.Context, BaseException], bool],
            Callable[[gproot.event.Context, BaseException], Awaitable[bool]]
        ]

        RedoHandler = Union[
            Callable[[gproot.event.Context,], bool],
            Callable[[gproot.event.Context,], Awaitable[bool]],
        ]

    class sub:
        EventHandler = Union[
            Callable[[gpsub.event.Context], None],
            Callable[[gpsub.event.Context], Awaitable[None]],
        ]

        ExceptionHandler = Union[
            Callable[[gpsub.event.Context, BaseException], bool],
            Callable[[gpsub.event.Context, BaseException], Awaitable[bool]]
        ]

        RedoHandler = Union[
            Callable[[gpsub.event.Context], bool],
            Callable[[gpsub.event.Context], Awaitable[bool]],
        ]
    

class _FrameBase(Protocol):
    def set_routine_timeout(self, timeout: float | None) -> None:
        ...
    def set_cleanup_timeout(self, timeout: float | None) -> None:
        ...
    def stop_routine(self) -> None:
        ...

    
class _RootFrameBase(_FrameBase, Protocol):
    def set_environments(self, environments: dict) -> None:
        ...
    def set_on_exception(self, handler: handler.root.ExceptionHandler) -> None:
        ...
    def set_on_redo(self, handler: handler.root.RedoHandler) -> None:
        ...
    def set_on_open(self, handler: handler.root.EventHandler) -> None:
        ...
    def set_on_start(self, handler: handler.root.EventHandler) -> None:
        ...
    def set_on_end(self, handler: handler.root.EventHandler) -> None:
        ...
    def set_on_cancel(self, handler: handler.root.EventHandler) -> None:
        ...
    def set_on_close(self, handler: handler.root.EventHandler) -> None:
        ...
    def start(self) -> ContextManager[FrameFuture]:
        ...

class frame:
    class RootFrame(_RootFrameBase, Protocol):
        def create_sub_frame(self, name: str, routine: routine.Sub) -> frame.SubFrame:
            ...

        def create_ipc_sub_frame(self, name: str, routine: routine.ipc.Sub) -> frame.SubFrame:
            ...

    class IPCRootFrame(_RootFrameBase, Protocol):
        pass
        
    class SubFrame(_FrameBase, Protocol):
        def set_on_exception(self, handler: handler.root.ExceptionHandler) -> None:
            ...
        def set_on_redo(self, handler: handler.sub.RedoHandler) -> None:
            ...
        def set_on_open(self, handler: handler.sub.EventHandler) -> None:
            ...
        def set_on_start(self, handler: handler.sub.EventHandler) -> None:
            ...
        def set_on_end(self, handler: handler.sub.EventHandler) -> None:
            ...
        def set_on_cancel(self, handler: handler.sub.EventHandler) -> None:
            ...
        def set_on_close(self, handler: handler.sub.EventHandler) -> None:
            ...

class FrameFuture(Protocol):
    @property
    def frame_name(self) -> str:
        ...
    def cancel(self):
        ...
    def wait_done(self, *, timeout: float | None = None, raises: bool = False) -> dict[str, BaseException | None]:
        ...
    def processing(self) -> bool:
        ...

def create_frame(frame_name: str, routine: routine.Root, *, logger: logging.Logger | None = None) -> frame.RootFrame:
    from gpframe._impl.frame.root import create_frame
    return create_frame(frame_name, routine, logger = logger)

def create_ipc_frame(frame_name: str, routine: routine.ipc.Root, *, logger: logging.Logger | None = None) -> frame.IPCRootFrame:
    from gpframe._impl.frame.root_ipc import create_ipc_frame
    return create_ipc_frame(frame_name, routine, logger = logger)

