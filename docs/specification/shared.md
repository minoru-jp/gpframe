<!-- Published from devdocs/canonical_documents/specification/shared.md sha256:a2e651db16247d6f5547c75809c48a869d0d85b941bdb719ae469cc2434443f0. Translated from the Japanese canonical document; edit the canonical source instead of this file. -->
# Shared

Rules on creating, reading, writing, and atomically updating `Shared`, a shared cell with a fixed type.

## SHARED_001

The `typ` of `Shared(typ, value)` must be a runtime class that can be checked with `isinstance()`, and must not be `NoneType`. If this is not satisfied, `DeclaredTypeError` is raised. Type expressions such as `list[int]` are rejected.

title: Declared type

level: MUST

## SHARED_002

The value held by `Shared` is always an instance of the declared type, and must not be `None`. The value at creation, the values passed to `set()` and `swap()`, and the result of the function of `apply()` are all checked against this condition. If it is not satisfied, `DeclaredTypeError` is raised and the value is not changed.

title: The value always matches the type

level: MUST

## SHARED_003

Type checking uses `isinstance()`. Instances of subclasses of the declared type are also accepted (`Shared(int, 0)` accepts `True`).

title: Subclass instances

level: INFORMATIVE

## SHARED_004

`get()` returns the current value. `set(value)` replaces the value. `swap(value)` replaces the value and returns the value from before the replacement.

title: Reading and replacing

level: MUST

## SHARED_005

`apply(fn)` passes the current value to `fn`, replaces the value with the result, and returns the value after the replacement. It performs everything from the read to the write as a single operation, and must not lose updates from concurrent `apply()`, `set()`, and `swap()`.

title: Atomic update

level: MUST

## SHARED_006

If the `fn` of `apply()` raises an exception, that exception is raised as is, and the value is not changed.

title: Failing update functions

level: MUST

## SHARED_007

The `fn` of `apply()` is called while the lock is held, so it should be a short function that has no side effects and does not operate on the same `Shared`.

title: Writing update functions

level: SHOULD

condition: When writing a function to pass to `apply()`.

## SHARED_008

To keep several values always consistent, an immutable data class should be put into a single `Shared` and replaced as a whole with `apply()`. No atomic operation spanning multiple `Shared` instances is provided.

title: Keeping several values consistent

level: SHOULD
