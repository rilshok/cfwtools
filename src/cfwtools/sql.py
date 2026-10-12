__all__ = [
    "Cursor",
    "Sql",
    "SqlStorage",
]

from collections.abc import Iterator
from typing import Protocol, Self, cast, overload

from jinja2 import Template

from cfwtools._utils import to_py
from cfwtools.template import Query


class _CursorRow(Protocol):
    def to_py(self) -> dict[str, str]: ...


class _CursorIterable(Protocol):
    def __iter__(self) -> Iterator[_CursorRow]: ...


class SqlStorage(Protocol):
    def exec(self, query: str, /, *bindings: object) -> _CursorIterable: ...


class Cursor[RowT = dict[str, str]]:
    def __init__(self, cursor: _CursorIterable) -> None:
        self._iter = iter(cursor)

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> RowT:
        data = to_py(next(self._iter))
        if not isinstance(data, dict):
            msg = f"Cursor row data must be a dict, got {type(data).__name__}"
            raise TypeError(msg)
        return cast("RowT", data)


class Sql:
    def __init__(self, sql: SqlStorage) -> None:
        self._sql = sql

    @overload
    def __call__[RowT](
        self,
        query: Query[RowT],
        /,
        **values: object,
    ) -> Cursor[RowT]: ...

    @overload
    def __call__(
        self,
        query: str | Template,
        /,
        **values: object,
    ) -> Cursor[dict[str, str]]: ...

    def __call__(
        self,
        query: Query[object] | str | Template,
        /,
        **values: object,
    ) -> Cursor[object]:
        if isinstance(query, str) and values:
            query = Query(query)
        if not isinstance(query, str):
            query = query.render(**values)
        return Cursor(self._sql.exec(query))
