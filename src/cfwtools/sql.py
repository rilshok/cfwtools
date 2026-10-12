__all__ = [
    "Cursor",
    "Sql",
    "SqlStorage",
]

from collections.abc import Callable, Iterator
from typing import Protocol, Self, overload

from cfwtools._utils import to_py
from cfwtools.template import Query


class _CursorRow(Protocol):
    def to_py(self) -> dict[str, str]: ...


class _CursorIterable(Protocol):
    def __iter__(self) -> Iterator[_CursorRow]: ...


class SqlStorage(Protocol):
    def exec(self, query: str, /, *bindings: object) -> _CursorIterable: ...


class Cursor[RowT = dict[str, str]]:
    def __init__(
        self,
        cursor: _CursorIterable,
        row_type: Callable[..., RowT],
    ) -> None:
        self._iter = iter(cursor)
        self._row_type = row_type

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> RowT:
        data = to_py(next(self._iter))
        if not isinstance(data, dict):
            msg = f"Cursor row data must be a dict, got {type(data).__name__}"
            raise TypeError(msg)
        return self._row_type(**data)


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
        query: str,
        /,
        **values: object,
    ) -> Cursor[dict[str, str]]: ...

    def __call__(
        self,
        query: Query[object] | str,
        /,
        **values: object,
    ) -> Cursor[object]:
        if isinstance(query, Query):
            return Cursor(
                cursor=self._sql.exec(query.render(**values)),
                row_type=query.row_type,
            )
        if values:
            query = Query(query).render(**values)
        return Cursor[dict[str, str]](
            cursor=self._sql.exec(query),
            row_type=dict,
        )
