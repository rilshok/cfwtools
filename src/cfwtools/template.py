__all__ = [
    "Query",
]

from collections.abc import Callable
from typing import Any, Final, overload

from jinja2 import Environment, StrictUndefined, Undefined

JINJA_ENV = Environment(undefined=StrictUndefined, autoescape=False)  # noqa: S701


def _safe_repr(value: object) -> str | Undefined:
    """Safely represent a value, preserving Undefined objects without conversion."""
    return value if isinstance(value, Undefined) else repr(value)


JINJA_ENV.filters["r"] = _safe_repr  # pyright: ignore[reportUnknownMemberType]


class Query[RowT = dict[str, str]]:
    """SQL Jinja2 template with the type its result rows are built into."""

    @overload
    def __init__(
        self: "Query[dict[str, str]]",
        source: str,
    ) -> None: ...

    @overload
    def __init__(
        self,
        source: str,
        row_type: Callable[..., RowT],
    ) -> None: ...

    def __init__(
        self,
        source: str,
        row_type: Callable[..., Any] = dict,
    ) -> None:
        self._template = JINJA_ENV.from_string(source)
        self.row_type: Final[Callable[..., RowT]] = row_type

    def render(self, **values: object) -> str:
        return self._template.render(**values)
