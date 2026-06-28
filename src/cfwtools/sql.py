from collections.abc import Iterator
from typing import Protocol, Self

from jinja2 import Template


class _CursorRow(Protocol):
    def to_py(self) -> dict[str, str]: ...


class _CursorIterable(Protocol):
    def __iter__(self) -> Iterator[_CursorRow]: ...


class _SqlStorage(Protocol):
    def exec(self, query: str, /, *bindings: object) -> _CursorIterable: ...


class Cursor:
    def __init__(self, cursor: _CursorIterable) -> None:
        self._iter = iter(cursor)

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> dict[str, str]:
        data: dict[str, str] | _CursorRow = next(self._iter)
        if (to_py := getattr(data, "to_py", None)) is not None:
            data = to_py()
        if not isinstance(data, dict):
            msg = f"Cursor row data must be a dict, got {type(data).__name__}"
            raise TypeError(msg)
        return data


class Sql:
    def __init__(self, sql: _SqlStorage) -> None:
        self._sql = sql

    def __call__(self, query: str | Template, /, **values: object) -> Cursor:
        if isinstance(query, Template):
            query = query.render(**values)
        return Cursor(self._sql.exec(query))
