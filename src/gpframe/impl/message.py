
from abc import ABC, abstractmethod
from enum import Enum
import threading
from typing import Any, Callable, TypeVar, cast, overload
from multiprocessing.managers import DictProxy

T = TypeVar("T")
D = TypeVar("D")

class _NO_DEFAULT(Enum):
    _ = "dummy member"

def _AllStr(v: str) -> bool:
    return True

def _AllInt(v: int) -> bool:
    return True

def _AllFloat(v: float) -> bool:
    return True

def _AllBool(v: bool) -> bool:
    return True

def _NoEffect(v: str) -> str:
    return v

class MessageReader(ABC):
    __slots__ = ()
    @abstractmethod
    def geta(self, key: Any, default: Any = _NO_DEFAULT) -> Any:
        ...
    @abstractmethod
    def getd(self, key: Any, typ: type[T], default: D) -> T | D:
        ...
    @abstractmethod
    def get(self, key: Any, typ: type[T]) -> T:
        ...
    @abstractmethod
    def string(
        self,
        key: Any,
        default: Any = _NO_DEFAULT,
        *,
        prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _NoEffect,
        valid: Callable[[str], bool] = _AllStr,
    ) -> str:
        ...
    @abstractmethod
    def string_to_int(
        self,
        key: Any,
        default: int | Any = _NO_DEFAULT,
        *,
        prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _NoEffect,
        valid: Callable[[int], bool] = _AllInt,
    ) -> int:
        ...
    @abstractmethod
    def string_to_float(
        self,
        key: Any,
        default: float | Any = _NO_DEFAULT,
        *,
        prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _NoEffect,
        valid: Callable[[float], bool] = _AllFloat,
    ) -> float:
        ...
    @abstractmethod
    def string_to_bool(
        self,
        key: Any,
        default: bool | Any = _NO_DEFAULT,
        *,
        prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _NoEffect,
        true: tuple[str, ...] = (),
        false: tuple[str, ...] = (),
        valid: Callable[[bool], bool] = _AllBool,
    ) -> bool:
        ...

class MessageUpdater(MessageReader):
    __slots__ = ()
    @abstractmethod
    def geta(self, key: Any, default: Any = _NO_DEFAULT) -> Any:
        ...
    @abstractmethod
    def getd(self, key: Any, typ: type[T], default: D) -> T | D:
        ...
    @abstractmethod
    def get(self, key: Any, typ: type[T]) -> T:
        ...
    @abstractmethod
    def update(self, key: Any, value: T) -> T:
        ...
    @abstractmethod
    def apply(self, key: Any, typ: type[T], fn: Callable[[T], T], default: T | type[_NO_DEFAULT] = _NO_DEFAULT) -> T:
        ...
    @abstractmethod
    def remove(self, key: Any, default: Any = None) -> Any:
        ...

class MessageRegistry:
    __slots__ = ("_usage_state_checker", "_lock", "_map", "_updater", "_reader")
    def __init__(
            self,
            lock: threading.Lock,
            map_: dict | DictProxy,
            usage_state_checker: Callable[[], None] | None = None
        ):
        self._usage_state_checker = usage_state_checker if usage_state_checker else lambda: None
        self._lock = lock
        self._map = map_
        self._updater = self._create_updater()
        self._reader = self._create_reader()
    
    def update_map_unsafe(self, other: dict):
        assert self._map is not None
        self._map.update(other)
    
    def geta(self, key: Any, default: Any = _NO_DEFAULT) -> Any:
        self._usage_state_checker()
        with self._lock:
            if self._map is not None:
                if key in self._map:
                    value = self._map[key]
                    return value
                else:
                    if default is _NO_DEFAULT:
                        raise KeyError
                    return default
            else:
                raise RuntimeError
    
    def getd(self, key: Any, typ: type[T], default: D) -> T | D:
        self._usage_state_checker()
        with self._lock:
            if self._map is not None:
                if key in self._map:
                    value = self._map[key]
                    if not isinstance(value, typ):
                        raise TypeError
                    return value
                else:
                    return default
            else:
                raise RuntimeError
    
    def get(self, key: Any, typ: type[T]) -> T:
        self._usage_state_checker()
        with self._lock:
            if self._map is not None:
                value = self._map[key]
                if not isinstance(value, typ):
                    raise TypeError
                return value
            else:
                raise RuntimeError
    
    def update(self, key: Any, value: T) -> T:
        self._usage_state_checker()
        with self._lock:
            if self._map is not None:
                self._map[key] = value
                return value
            else:
                raise RuntimeError
    
    def apply(self, key: Any, typ: type[T], fn: Callable[[T], T], default: T | type[_NO_DEFAULT] = _NO_DEFAULT) -> T:
        self._usage_state_checker()
        with self._lock:
            if self._map is not None:
                if key in self._map:
                    value = self._map[key]
                else:
                    if default is not _NO_DEFAULT:
                        value = default
                    else:
                        raise KeyError
                if isinstance(value, typ):
                    applied_value = fn(value)
                    self._map[key] = applied_value
                    return applied_value
                else:
                    raise TypeError
            else:
                raise RuntimeError
    
    def remove(self, key: Any, default: Any = None) -> Any:
        self._usage_state_checker()
        with self._lock:
            if self._map is not None:
                return self._map.pop(key, default)
            else:
                raise RuntimeError
    
    def _value_with_returns_with_default(self, key: Any, default: Any, typ: type[T]) -> tuple[T, bool]:
        self._usage_state_checker()
        with self._lock:
            if self._map is not None:
                if key in self._map:
                    return self._map[key], False
                else:
                    if isinstance(default, typ):
                        return default, True
                    if default is _NO_DEFAULT:
                        raise KeyError
                    return default, False                    
            else:
                raise RuntimeError
    
    def string(
        self,
        key: Any,
        default: Any = _NO_DEFAULT,
        *,
        prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _NoEffect,
        valid: Callable[[str], bool] = _AllStr,
    ) -> str:
        string = str(self.geta(key, default))
        for pre_proc in prep if isinstance(prep, tuple) else (prep,):
            string = pre_proc(string)
        if not valid(string):
            raise ValueError
        return string

    def string_to_int(
        self,
        key: Any,
        default: int | Any = _NO_DEFAULT,
        *,
        prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _NoEffect,
        valid: Callable[[int], bool] = _AllInt,
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
        key: Any,
        default: float | Any = _NO_DEFAULT,
        *,
        prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _NoEffect,
        valid: Callable[[float], bool] = _AllFloat,
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
        key: Any,
        default: bool | Any = _NO_DEFAULT,
        *,
        prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _NoEffect,
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
        self._usage_state_checker()
        with self._lock:
            if self._map is not None:
                return str(self._map)
            else:
                return "!!MessageRegistry is cleanuped."

    def _create_updater(self):
        outer = self
        class _Updater(MessageUpdater):
            __slots__ = ()
            def geta(self, key: Any, default: Any = _NO_DEFAULT) -> Any:
                return outer.geta(key, default)
            def getd(self, key: Any, typ: type[T], default: D) -> T | D:
                return outer.getd(key, typ, default)
            def get(self, key: Any, typ: type[T]) -> T:
                return outer.get(key, typ)
            def update(self, key: Any, value: T) -> T:
                return outer.update(key, value)
            def apply(self, key: Any, typ: type[T], fn: Callable[[T], T], default: T | type[_NO_DEFAULT] = _NO_DEFAULT) -> T:
                return outer.apply(key, typ, fn, default)
            def remove(self, key: Any, default: Any = None) -> Any:
                return outer.remove(key, default)
            def string(
                self,
                key: Any,
                default: Any = _NO_DEFAULT,
                *,
                prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _NoEffect,
                valid: Callable[[str], bool] = _AllStr,
            ) -> str:
                return outer.string(key, default, prep = prep, valid = valid)
            def string_to_int(
                self,
                key: Any,
                default: int | Any = _NO_DEFAULT,
                *,
                prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _NoEffect,
                valid: Callable[[int], bool] = _AllInt,
            ) -> int:
                return outer.string_to_int(key, default, prep = prep, valid = valid)
            def string_to_float(
                self,
                key: Any,
                default: float | Any = _NO_DEFAULT,
                *,
                prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _NoEffect,
                valid: Callable[[float], bool] = _AllFloat,
            ) -> float:
                return outer.string_to_float(key, default, prep = prep, valid = valid)
            def string_to_bool(
                self,
                key: Any,
                default: bool | Any = _NO_DEFAULT,
                *,
                prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _NoEffect,
                true: tuple[str, ...] = (),
                false: tuple[str, ...] = (),
            ) -> bool:
                return outer.string_to_bool(key, default, prep = prep, true = true, false = false)
            def __str__(self):
                return outer.__str__()
            def __reduce__(self):
                outer._usage_state_checker()
                with outer._lock:
                    if outer._map is not None:
                        return (_create_message_updater, (outer._lock, outer._map))
                    else:
                        raise RuntimeError("map is cleared")
        return _Updater()

    def _create_reader(self):
        outer = self
        class _Reader(MessageReader):
            __slots__ = ()
            def geta(self, key: Any, default: Any = _NO_DEFAULT) -> Any:
                return outer.geta(key, default)
            def getd(self, key: Any, typ: type[T], default: D) -> T | D:
                return outer.getd(key, typ, default)
            def get(self, key: Any, typ: type[T]) -> T:
                return outer.get(key, typ)
            def string(
                self,
                key: Any,
                default: Any = _NO_DEFAULT,
                *,
                prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _NoEffect,
                valid: Callable[[str], bool] = _AllStr,
            ) -> str:
                return outer.string(key, default, prep = prep, valid = valid)
            def string_to_int(
                self,
                key: Any,
                default: int | Any = _NO_DEFAULT,
                *,
                prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _NoEffect,
                valid: Callable[[int], bool] = _AllInt,
            ) -> int:
                return outer.string_to_int(key, default, prep = prep, valid = valid)
            def string_to_float(
                self,
                key: Any,
                default: float | Any = _NO_DEFAULT,
                *,
                prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _NoEffect,
                valid: Callable[[float], bool] = _AllFloat,
            ) -> float:
                return outer.string_to_float(key, default, prep = prep, valid = valid)
            def string_to_bool(
                self,
                key: Any,
                default: bool | Any = _NO_DEFAULT,
                *,
                prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _NoEffect,
                true: tuple[str, ...] = (),
                false: tuple[str, ...] = (),
            ) -> bool:
                return outer.string_to_bool(key, default, prep = prep, true = true, false = false)
            def __str__(self):
                return outer.__str__()
            def __reduce__(self):
                outer._usage_state_checker()
                with outer._lock:
                    if outer._map is not None:
                        return (_create_message_reader, (outer._lock, outer._map))
                    else:
                        raise RuntimeError("map is cleared")

        return _Reader()
    
    @property
    def updater(self):
        return self._updater
    
    @property
    def reader(self):
        return self._reader
    
    def copy_map_without_usage_state_check(self) -> dict:
        with self._lock:
            if self._map is not None:
                return dict(self._map)
            else:
                raise RuntimeError("map is cleared")
    
    def clear_map_unsafe(self) -> None:
        if self._map is not None:
            self._map.clear()
            self._map = None
    
    def __reduce__(self):
        return (MessageRegistry, (self._lock, self._map))


def _create_message_updater(
        lock_: threading.Lock,
        map_: dict | DictProxy
) -> MessageUpdater:
    return MessageRegistry(lock_, map_).updater

def _create_message_reader(
        lock_: threading.Lock,
        map_: dict | DictProxy
) -> MessageReader:    
    return MessageRegistry(lock_, map_).reader

