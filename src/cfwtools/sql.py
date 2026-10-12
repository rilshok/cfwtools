__all__ = [
    "Query",
    "Sql",
    "SqlStorage",
]

from collections.abc import Callable, Iterator
from typing import Any, Final, Protocol, overload

from jinja2 import Environment, StrictUndefined, Template, Undefined, meta

from cfwtools._utils import to_py

JINJA_ENV = Environment(undefined=StrictUndefined, autoescape=False)  # noqa: S701


def _safe_repr(value: object) -> str | Undefined:
    """Safely represent a value, preserving Undefined objects without conversion."""
    return value if isinstance(value, Undefined) else repr(value)


JINJA_ENV.filters["r"] = _safe_repr  # pyright: ignore[reportUnknownMemberType]
_JINJA_MARKERS = (
    JINJA_ENV.block_start_string,
    JINJA_ENV.variable_start_string,
    JINJA_ENV.comment_start_string,
)


class _CursorRow(Protocol):
    def to_py(self) -> dict[str, str]: ...


class _CursorIterable(Protocol):
    def __iter__(self) -> Iterator[_CursorRow]: ...


class SqlStorage(Protocol):
    def exec(self, query: str, /, *bindings: object) -> _CursorIterable: ...


class Query[RowT = dict[str, str]]:
    """SQL Jinja2 template with the type its result rows are built into."""

    @overload
    def __init__(
        self: "Query[dict[str, str]]",
        sql: str,
    ) -> None: ...

    @overload
    def __init__(
        self,
        sql: str,
        row_type: Callable[..., RowT],
    ) -> None: ...

    def __init__(
        self,
        sql: str,
        row_type: Callable[..., Any] = dict,
    ) -> None:
        self._row_type: Final[Callable[..., RowT]] = row_type
        self._sql: Final[Template | str]
        self._variables: Final[frozenset[str]]
        if any(marker in sql for marker in _JINJA_MARKERS):
            ast = JINJA_ENV.parse(sql)
            self._sql = JINJA_ENV.from_string(ast)
            self._variables = frozenset(meta.find_undeclared_variables(ast))
        else:
            self._sql = sql
            self._variables = frozenset()

    def render(self, **values: object) -> str:
        if unexpected := values.keys() - self._variables:
            msg = f"Unexpected query values: {', '.join(sorted(unexpected))}"
            raise TypeError(msg)
        if isinstance(self._sql, str):
            return self._sql
        return self._sql.render(**values)

    def __call__(
        self,
        execute: Callable[[str], _CursorIterable],
        /,
        **values: object,
    ) -> Iterator[RowT]:
        """Execute the rendered query and build a `row_type` object per row."""
        return map(self._build_row, execute(self.render(**values)))

    def _build_row(self, row: _CursorRow) -> RowT:
        data = to_py(row)
        if not isinstance(data, dict):
            msg = f"Row data must be a dict, got {type(data).__name__}"
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
    ) -> Iterator[RowT]: ...

    @overload
    def __call__(
        self,
        query: str,
        /,
        **values: object,
    ) -> Iterator[dict[str, str]]: ...

    def __call__(
        self,
        query: Query[object] | str,
        /,
        **values: object,
    ) -> Iterator[object]:
        if isinstance(query, str):
            query = Query(query)
        return query(self._sql.exec, **values)
