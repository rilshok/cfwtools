from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator, Mapping
from typing import Any

from cfwtools.durable_object import DurableObject
from cfwtools.sql import Sql
from cfwtools.template import template


class Default:
    def __init__(self, default_fn: Callable[[], str]) -> None:
        self._fn = default_fn

    def __get__[T](
        self,
        instance: "Variable[T] | None",
        owner: "type[Variable[T]]",
    ) -> str:
        return self._fn()


class Variable[T](ABC):
    default: str | Default = ""

    @classmethod
    def key_str(cls) -> str:
        return cls.__name__.lower()

    def __init__(self, raw: str) -> None:
        self.raw = raw

    @property
    @abstractmethod
    def value(self) -> T:
        raise NotImplementedError

    @abstractmethod
    def validate(self, variables: "Variables") -> str | None:
        raise NotImplementedError


_CREATE_TABLE_VARIABLES = """
CREATE TABLE IF NOT EXISTS __variables__ (
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (key)
);
"""

_UPDATE_VARIABLES = template("""
INSERT OR REPLACE INTO __variables__ (key, value)
VALUES ({{ key | r }}, {{ value | r }});
""")


class _Variables:
    def __init__(self, sql: Sql, *variable_types: type[Variable[Any]]) -> None:
        self._sql = sql
        self._sql(_CREATE_TABLE_VARIABLES)
        self._mapping: dict[type[Variable[Any]], Variable[Any]] = {}

        variable_mapping = {t.key_str(): t for t in variable_types}
        for row in self._sql("SELECT key, value FROM __variables__"):
            key, value = row["key"], row["value"]
            if key not in variable_mapping:
                continue
            variable_cls = variable_mapping.pop(key)
            variable = variable_cls(value)
            self._mapping[variable_cls] = variable

        variables_update: dict[str, str] = {}
        for variable_cls in variable_mapping.values():
            if value := variable_cls.default:
                variables_update[variable_cls.key_str()] = value
            self._mapping[variable_cls] = variable_cls(value)

        for key, value in variables_update.items():
            self._sql(_UPDATE_VARIABLES, key=key, value=value)

        for variable in self._mapping.values():
            self._assert_variable(variable)

    def _assert_variable(self, variable: Variable[Any]) -> None:
        error = variable.validate(self.read_only)
        if error is not None:
            msg = f"{variable.key_str()}: {error}"
            raise SystemError(msg)

    def __contains__(self, key: type[Variable[Any]]) -> bool:
        return key in self._mapping

    def __getitem__[T](self, key: type[Variable[T]]) -> T:
        return self._mapping[key].value

    def __setitem__(self, key: type[Variable[Any]], value: str) -> None:
        if not value:
            msg = f"{key.__name__}: A variable can't be an empty value"
            raise ValueError(msg)
        if key not in self._mapping:
            msg = f"Variable not registered: {key.__name__}"
            raise KeyError(msg)
        variable = key(value)
        self._assert_variable(variable)
        self._sql(_UPDATE_VARIABLES, key=variable.key_str(), value=value)
        self._mapping[key] = variable

    def to_dict(self) -> dict[str, str]:
        return {
            variable_cls.key_str(): variable.raw
            for variable_cls, variable in self._mapping.items()
        }

    def from_key(self, key: str) -> type[Variable[Any]]:
        for variable_cls in self._mapping:
            if variable_cls.key_str() == key:
                return variable_cls
        raise KeyError(key)

    @property
    def read_only(self) -> "Variables":
        return Variables(self)

    def assert_contains(self, key: type[Variable[Any]]) -> None:
        if key in self:
            return
        msg = f"{key.__name__} is not configured"
        raise SystemError(msg)

    def __iter__(self) -> Iterator[type[Variable[Any]]]:
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._mapping)


class Variables(Mapping[type[Variable[Any]], Any]):
    def __init__(self, backend: _Variables) -> None:
        self._backend = backend

    def __contains__(self, key: object) -> bool:
        try:
            return (
                isinstance(key, type)
                and issubclass(key, Variable)
                and key in self._backend
            )
        except TypeError:
            return False

    def __getitem__[T](self, key: type[Variable[T]]) -> T:
        return self._backend[key]

    def __iter__(self) -> Iterator[type[Variable[Any]]]:
        return iter(self._backend)

    def __len__(self) -> int:
        return len(self._backend)


class DurableObjectWithVariables(DurableObject):
    """Durable Object with built-in variable management in SQLite.

    Extends DurableObject with functionality for secure storage and management
    of variables (API keys, tokens, etc.) in local database with validation.

    Usage:
        1. Define Variable subclasses with validation logic:

            class ApiKey(Variable[str]):
                default = "default_key"  # or Default(lambda: ...)

                @property
                def value(self) -> str:
                    return self.raw

                def validate(self, variables: Variables) -> str | None:
                    if len(self.raw) < 32:
                        return "Key must be at least 32 characters"
                    return None

        2. Create a DurableObjectWithVariables subclass with registered variables:

            class UserDO(DurableObjectWithVariables,
                         variables=[ApiKey, JwtVariable]):
                async def some_method(self):
                    # Access variables via self.variables[VariableClass]
                    api_key = self.variables[ApiKey]  # Gets the value
                    # or raw value: self.variables[ApiKey].raw

    Features:
        - Variables stored in SQLite 'variable' table
        - Default values used on initialization (if set)
        - Automatic validation on creation and updates
        - RPC methods for remote variable management
        - Complex type support via Variable property methods

    Attributes:
        variable_types: Registered variable types
            (set via __init_subclass__)
        variables: Internal _Variables object for storage
    """

    variable_types: list[type[Variable[Any]]]

    def __init_subclass__(
        cls,
        *,
        variables: list[type[Variable[Any]]] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init_subclass__(**kwargs)  # type: ignore[misc]
        cls.variable_types = variables or []

    def __init__(self, ctx, env) -> None:
        self.variables = _Variables(Sql(ctx.storage.sql), *self.variable_types)
        super().__init__(ctx, env)

    async def get_variables(self) -> dict[str, str]:
        """Get all registered variables as a dictionary.

        Returns:
            Dictionary mapping variable names (lowercase class names) to their
            raw string values. Example: {"apikey": "variable_value", ...}
        """
        return self.variables.to_dict()

    async def change_variable(self, key: str, value: str) -> str:
        """Update a variable value with validation.

        Args:
            key: Variable name (lowercase class name, e.g. "apikey")
            value: New variable value to set

        Returns:
            Empty string on success, error message on failure.
            Validation errors from the Variable class are included.
        """
        try:
            variable_cls = self.variables.from_key(key)
            self.variables[variable_cls] = value
        except Exception as exc:  # noqa: BLE001
            return str(exc)
        else:
            return ""
