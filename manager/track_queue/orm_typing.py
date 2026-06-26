from __future__ import annotations

from typing import SupportsInt, TypeVar, cast

from sqlalchemy.sql.elements import ColumnElement

_T = TypeVar("_T")


def sql_bool(expression: object) -> ColumnElement[bool]:
    return cast(ColumnElement[bool], expression)


def orm_int(value: object) -> int:
    return int(cast(SupportsInt, value))


def rowcount(result: object) -> int:
    value = getattr(result, "rowcount", 0)
    if callable(value):
        value = value()
    return int(cast(SupportsInt, value or 0))


def optional_row(value: object, row_type: type[_T]) -> _T | None:
    if value is None:
        return None
    if not isinstance(value, row_type):
        raise TypeError(f"expected {row_type.__name__}, got {type(value).__name__}")
    return value
