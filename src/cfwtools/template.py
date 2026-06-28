__all__ = [
    "template",
]

from jinja2 import Environment, StrictUndefined, Template, Undefined

JINJA_ENV = Environment(undefined=StrictUndefined, autoescape=True)


def _safe_repr(value: object) -> str | Undefined:
    """Safely represent a value, preserving Undefined objects without conversion."""
    return value if isinstance(value, Undefined) else repr(value)


JINJA_ENV.filters["r"] = _safe_repr  # pyright: ignore[reportUnknownMemberType]


def template(source: str) -> Template:
    """Create a Jinja2 template from a source string with strict undefined handling."""
    return JINJA_ENV.from_string(source)
