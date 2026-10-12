__all__ = [
    "Query",
]

from jinja2 import Environment, StrictUndefined, Undefined

JINJA_ENV = Environment(undefined=StrictUndefined, autoescape=False)  # noqa: S701


def _safe_repr(value: object) -> str | Undefined:
    """Safely represent a value, preserving Undefined objects without conversion."""
    return value if isinstance(value, Undefined) else repr(value)


JINJA_ENV.filters["r"] = _safe_repr  # pyright: ignore[reportUnknownMemberType]


class Query[RowT = dict[str, str]]:
    """SQL Jinja2 template annotated with the row type it produces.

    `RowT` is a phantom type parameter: it is never checked at runtime.
    """

    def __init__(self, source: str) -> None:
        self._template = JINJA_ENV.from_string(source)

    def render(self, **values: object) -> str:
        return self._template.render(**values)
