
from typing import Any, Callable

from gpframe.contracts.protocols import message
MessageReader = message.MessageReader
MessageUpdater = message.MessageUpdater

from gpframe._impl.message.message import MessageRegistry
from gpframe.contracts.protocols import _NO_DEFAULT, _D, _T, _any_float, _any_int, _any_str, _noop

class MessageReflector:
    __slots__ = ("_reader", "_updater")

    def __init__(self, namespace: str, message: MessageRegistry[str]):
        self._reader = self._create_ipc_message_reader_reflector(
            namespace,
            message
        )
        self._updater = self._create_ipc_message_updater_reflector(
            namespace,
            self._reader,
            message
        )
    
    @property
    def reader(self) -> MessageReader[str]:
        return self._reader
    
    @property
    def updater(self) -> MessageUpdater[str]:
        return self._updater

    def _create_ipc_message_reader_reflector(
            self,
            namespace: str,
            message: MessageRegistry[str]
    ) -> MessageReader[str]:
        
        class _Interface(MessageReader):
            def geta(self, key: str, default: Any = _NO_DEFAULT) -> Any:
                return message.geta(namespace + str(key), default)
            
            def getd(self, key: str, typ: type[_T], default: _D) -> _T | _D:
                return message.getd(namespace + str(key), typ, default)
            def get(self, key: str, typ: type[_T]) -> _T:
                return message.get(namespace + str(key), typ)
            def string(
                self,
                key: str,
                default: Any = _NO_DEFAULT,
                *,
                prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
                valid: Callable[[str], bool] = _any_str,
            ) -> str:
                return message.string(namespace + str(key), default, prep = prep, valid = valid)
            def string_to_int(
                self,
                key: str,
                default: int | Any = _NO_DEFAULT,
                *,
                prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
                valid: Callable[[int], bool] = _any_int,
            ) -> int:
                return message.string_to_int(namespace + str(key), default, prep = prep, valid = valid)
            def string_to_float(
                self,
                key: str,
                default: float | Any = _NO_DEFAULT,
                *,
                prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
                valid: Callable[[float], bool] = _any_float,
            ) -> float:
                return message.string_to_float(namespace + str(key), default, prep = prep, valid = valid)
            def string_to_bool(
                self,
                key: str,
                default: bool | Any = _NO_DEFAULT,
                *,
                prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
                true: tuple[str, ...] = (),
                false: tuple[str, ...] = (),
            ) -> bool:
                return message.string_to_bool(namespace + str(key), default, prep = prep, true = true, false = false)
            
            def __reduce__(self):
                return (_reduce_reader, (namespace, message))

        return _Interface()

    def _create_ipc_message_updater_reflector(
            self,
            namespace: str,
            reader: MessageReader[str],
            message: MessageRegistry[str]
    ) -> MessageUpdater[str]:
        
        class _Interface(MessageUpdater, type(reader)):
            __slots__ = ()
            def update(self, key: str, value: _T) -> _T:
                return message.update(namespace + str(key), value)
            
            def apply(self, key: str, typ: type[_T], fn: Callable[[_T], _T], default: _T | type[_NO_DEFAULT] = _NO_DEFAULT) -> _T:
                return message.apply(namespace + str(key), typ, fn, default)
            
            def remove(self, key: str, default: Any = None) -> Any:
                return message.remove(namespace + str(key), default)
            
            def __reduce__(self):
                return (_reduce_updater, (namespace, message))
        
        return _Interface() # type: ignore

def _reduce_reader(namespace: str, message: MessageRegistry[str]):
    refl = MessageReflector(namespace, message)
    return refl.reader

def _reduce_updater(namespace: str, message: MessageRegistry[str]):
    refl = MessageReflector(namespace, message)
    return refl.updater



