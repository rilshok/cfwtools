from typing import Any

from jinja2 import Environment, StrictUndefined, Template, Undefined

JINJA_ENV = Environment(undefined=StrictUndefined)


def _safe_repr(value: Any) -> str | Undefined:
    """Safely represent a value, preserving Undefined objects without conversion."""
    return value if isinstance(value, Undefined) else repr(value)


JINJA_ENV.filters["r"] = _safe_repr


def template(source: str) -> Template:
    """Create a Jinja2 template from a source string with strict undefined handling."""
    return JINJA_ENV.from_string(source)
