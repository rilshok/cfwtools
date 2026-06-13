from typing import Any, Protocol, Iterator, Self
from jinja2 import Template


class _CursorRow(Protocol):
    def to_py(self) -> dict[str, str]: ...


class _CursorIterable(Protocol):
    def __iter__(self) -> Iterator[_CursorRow]: ...


class _SqlStorage(Protocol):
    def exec(self, query: str, /, *bindings: Any) -> _CursorIterable: ...


class Cursor:
    def __init__(self, cursor: _CursorIterable) -> None:
        self._iter = iter(cursor)

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> dict[str, str]:
        return next(self._iter).to_py()


class Sql:
    def __init__(self, sql: _SqlStorage) -> None:
        self._sql = sql

    def __call__(self, query: str | Template, /, **values: Any) -> Cursor:
        if isinstance(query, Template):
            query = query.render(**values)
        return Cursor(self._sql.exec(query))
