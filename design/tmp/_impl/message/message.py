
import threading
from typing import Any, Callable, Generic, cast


from gpframe._impl.common import (
    _K, _T, _D,
    _noop,
    _any_str,
    _any_int,
    _any_float,
    _NO_DEFAULT,
)
from gpframe.contracts.api import message

from gpframe._impl.protocols import _DictLike

class MessageRegistry(Generic[_K]):
    __slots__ = ("phase_validator", "_lock", "_map", "_updater", "_reader")
    def __init__(
            self,
            lock: threading.Lock,
            map_: _DictLike,
            phase_validtor: Callable[[], None] | None = None
        ):
        # Warning: Phase check is not performed when passing to subprocess
        self.phase_validator = phase_validtor if phase_validtor else lambda: None
        self._lock = lock
        self._map = map_
        self._reader = self._create_reader()
        self._updater = self._create_updater(type(self._reader))
        
    
    def update_map_unsafe(self, other: dict):
        self._map.update(other)
    
    def geta(self, key: _K, default: Any = _NO_DEFAULT) -> Any:
        self.phase_validator()
        with self._lock:
            if key in self._map:
                value = self._map[key]
                return value
            else:
                if default is _NO_DEFAULT:
                    raise KeyError
                return default
    
    def getd(self, key: _K, typ: type[_T], default: _D) -> _T | _D:
        self.phase_validator()
        with self._lock:
            if key in self._map:
                value = self._map[key]
                if not isinstance(value, typ):
                    raise TypeError
                return value
            else:
                return default
    
    def get(self, key: _K, typ: type[_T]) -> _T:
        self.phase_validator()
        with self._lock:
            value = self._map[key]
            if not isinstance(value, typ):
                raise TypeError
            return value

    def update(self, key: _K, value: _T) -> _T:
        self.phase_validator()
        with self._lock:
            self._map[key] = value
            return value
    
    def apply(self, key: Any, typ: type[_T], fn: Callable[[_T], _T], default: _T | type[_NO_DEFAULT] = _NO_DEFAULT) -> _T:
        self.phase_validator()
        with self._lock:
            if key in self._map:
                value = self._map[key]
            else:
                if default is not _NO_DEFAULT:
                    if isinstance(default, typ):
                        self._map[key] = default
                    else:
                        raise TypeError
                    return default
                else:
                    raise KeyError
            if isinstance(value, typ):
                applied_value = fn(value)
                if isinstance(applied_value, typ):
                    raise TypeError
                self._map[key] = applied_value
                return applied_value
            else:
                raise TypeError
    
    def remove(self, key: _K, default: Any = None) -> Any:
        self.phase_validator()
        with self._lock:
            return self._map.pop(key, default)
    
    def _value_with_returns_with_default(self, key: _K, default: Any, typ: type[_T]) -> tuple[_T, bool]:
        self.phase_validator()
        with self._lock:
            if key in self._map:
                return self._map[key], False
            else:
                if isinstance(default, typ):
                    return default, True
                if default is _NO_DEFAULT:
                    raise KeyError
                return default, False
    
    def string(
        self,
        key: _K,
        default: Any = _NO_DEFAULT,
        *,
        prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
        valid: Callable[[str], bool] = _any_str,
    ) -> str:
        string = str(self.geta(key, default))
        for pre_proc in prep if isinstance(prep, tuple) else (prep,):
            string = pre_proc(string)
        if not valid(string):
            raise ValueError
        return string

    def string_to_int(
        self,
        key: _K,
        default: int | Any = _NO_DEFAULT,
        *,
        prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
        valid: Callable[[int], bool] = _any_int,
    ) -> int:
        value, returns_with_default = self._value_with_returns_with_default(key, default, int)
        if returns_with_default:
            return default
        string = str(value)
        for pre_proc in prep if isinstance(prep, tuple) else (prep,):
            string = pre_proc(string)
        integer = int(string, 0)
        if not valid(integer):
            raise ValueError
        return integer

    def string_to_float(
        self,
        key: _K,
        default: float | Any = _NO_DEFAULT,
        *,
        prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
        valid: Callable[[float], bool] = _any_float,
    ) -> float:
        value, returns_with_default = self._value_with_returns_with_default(key, default, float)
        if returns_with_default:
            return default
        string = str(value)
        for pre_proc in prep if isinstance(prep, tuple) else (prep,):
            string = pre_proc(string)
        float_value = float(string)
        if not valid(float_value):
            raise ValueError
        return float_value

    def string_to_bool(
        self,
        key: _K,
        default: bool | Any = _NO_DEFAULT,
        *,
        prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
        true: tuple[str, ...] = (),
        false: tuple[str, ...] = (),
    ) -> bool:
        value, returns_with_default = self._value_with_returns_with_default(key, default, bool)
        if returns_with_default:
            return default
        string = str(value)
        for pre_proc in prep if isinstance(prep, tuple) else (prep,):
            string = pre_proc(string)
        if not true and not false:
            return bool(string)
        if true and not false:
            return string in true
        if false and not true:
            return string not in false
        if string in true:
            return True
        if string in false:
            return False
        raise ValueError(f"{key}: expected one of {true + false}, but got '{string}'")
        
    
    def __str__(self):
        self.phase_validator()
        with self._lock:
            return str(self._map)

    def _create_reader(self) -> message.MessageReader[_K]:
        outer = self
        class _Reader(message.MessageReader):
            __slots__ = ()
            def geta(self, key: _K, default: Any = _NO_DEFAULT) -> Any:
                return outer.geta(key, default)
            def getd(self, key: _K, typ: type[_T], default: _D) -> _T | _D:
                return outer.getd(key, typ, default)
            def get(self, key: _K, typ: type[_T]) -> _T:
                return outer.get(key, typ)
            def string(
                self,
                key: Any,
                default: Any = _NO_DEFAULT,
                *,
                prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
                valid: Callable[[str], bool] = _any_str,
            ) -> str:
                return outer.string(key, default, prep = prep, valid = valid)
            def string_to_int(
                self,
                key: _K,
                default: int | Any = _NO_DEFAULT,
                *,
                prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
                valid: Callable[[int], bool] = _any_int,
            ) -> int:
                return outer.string_to_int(key, default, prep = prep, valid = valid)
            def string_to_float(
                self,
                key: _K,
                default: float | Any = _NO_DEFAULT,
                *,
                prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
                valid: Callable[[float], bool] = _any_float,
            ) -> float:
                return outer.string_to_float(key, default, prep = prep, valid = valid)
            def string_to_bool(
                self,
                key: _K,
                default: bool | Any = _NO_DEFAULT,
                *,
                prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
                true: tuple[str, ...] = (),
                false: tuple[str, ...] = (),
            ) -> bool:
                return outer.string_to_bool(key, default, prep = prep, true = true, false = false)
            def __str__(self):
                return outer.__str__()
            def __reduce__(self):
                outer.phase_validator()
                with outer._lock:
                    return (_create_message_reader, (outer._lock, outer._map))

        return _Reader()

    def _create_updater(self, reader_type: type[message.MessageReader[_K]]) -> message.MessageUpdater[_K]:
        outer = self
        class _Updater(message.MessageUpdater, reader_type):
            __slots__ = ()
            def update(self, key: _K, value: _T) -> _T:
                return outer.update(key, value)
            def apply(self, key: _K, typ: type[_T], fn: Callable[[_T], _T], default: _T | type[_NO_DEFAULT] = _NO_DEFAULT) -> _T:
                return outer.apply(key, typ, fn, default)
            def remove(self, key: _K, default: Any = None) -> Any:
                return outer.remove(key, default)
            def __reduce__(self):
                outer.phase_validator()
                with outer._lock:
                    return (_create_message_updater, (outer._lock, outer._map))

        return _Updater() # type: ignore

    
    @property
    def updater(self) -> message.MessageUpdater[_K]:
        return self._updater
    
    @property
    def reader(self) -> message.MessageReader[_K]:
        return self._reader
    
    def __reduce__(self):
        return (MessageRegistry, (self._lock, self._map))


def _create_message_updater(
        lock_: threading.Lock,
        map_: _DictLike
) -> message.MessageUpdater:
    return MessageRegistry(lock_, map_).updater

def _create_message_reader(
        lock_: threading.Lock,
        map_: _DictLike
) -> message.MessageReader:
    return MessageRegistry(lock_, map_).reader

