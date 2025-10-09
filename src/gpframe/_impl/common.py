
from enum import Enum
from typing import Hashable, TypeVar


_T = TypeVar("_T")
_D = TypeVar("_D")
_K = TypeVar("_K", contravariant = True, bound = Hashable)

class _NO_DEFAULT(Enum):
    _ = "dummy member"

def _any_str(v: str) -> bool:
    return True
def _any_int(v: int) -> bool:
    return True
def _any_float(v: float) -> bool:
    return True
def _noop(v: str) -> str:
    return v
