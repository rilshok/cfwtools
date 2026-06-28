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
        instance: "Secret[T] | None",
        owner: "type[Secret[T]]",
    ) -> str:
        return self._fn()


class Secret[T](ABC):
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
    def validate(self, secrets: "Secrets") -> str | None:
        raise NotImplementedError


_CREATE_TABLE_SECRET = """
CREATE TABLE IF NOT EXISTS secret (
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (key)
);
"""  # noqa: S105

_UPDATE_SECRET = template("""
INSERT OR REPLACE INTO secret (key, value)
VALUES ({{ key | r }}, {{ value | r }});
""")


class _Secrets:
    def __init__(self, sql: Sql, *secret_types: type[Secret[Any]]) -> None:
        self._sql = sql
        self._sql(_CREATE_TABLE_SECRET)
        self._mapping: dict[type[Secret[Any]], Secret[Any]] = {}

        secret_mapping = {t.key_str(): t for t in secret_types}
        for row in self._sql("SELECT key, value FROM secret"):
            key, value = row["key"], row["value"]
            if key not in secret_mapping:
                continue
            secret_cls = secret_mapping.pop(key)
            secret = secret_cls(value)
            self._mapping[secret_cls] = secret

        secrets_update: dict[str, str] = {}
        for secret_cls in secret_mapping.values():
            if value := secret_cls.default:
                secrets_update[secret_cls.key_str()] = value
            self._mapping[secret_cls] = secret_cls(value)

        for key, value in secrets_update.items():
            self._sql(_UPDATE_SECRET, key=key, value=value)

        for secret in self._mapping.values():
            self._assert_secret(secret)

    def _assert_secret(self, secret: Secret[Any]) -> None:
        error = secret.validate(self.read_only)
        if error is not None:
            msg = f"{secret.key_str()}: {error}"
            raise SystemError(msg)

    def __contains__(self, key: type[Secret[Any]]) -> bool:
        return key in self._mapping

    def __getitem__[T](self, key: type[Secret[T]]) -> T:
        return self._mapping[key].value

    def __setitem__(self, key: type[Secret[Any]], value: str) -> None:
        if not value:
            msg = f"{key.__name__}: A secret can't be an empty value"
            raise ValueError(msg)
        if key not in self._mapping:
            msg = f"Secret not registered: {key.__name__}"
            raise KeyError(msg)
        secret = key(value)
        self._assert_secret(secret)
        self._sql(_UPDATE_SECRET, key=secret.key_str(), value=value)
        self._mapping[key] = secret

    def to_dict(self) -> dict[str, str]:
        return {
            secret_cls.key_str(): secret.raw
            for secret_cls, secret in self._mapping.items()
        }

    def from_key(self, key: str) -> type[Secret[Any]]:
        for secret_cls in self._mapping:
            if secret_cls.key_str() == key:
                return secret_cls
        raise KeyError(key)

    @property
    def read_only(self) -> "Secrets":
        return Secrets(self)

    def assert_contains(self, key: type[Secret[Any]]) -> None:
        if key in self:
            return
        msg = f"{key.__name__} is not configured"
        raise SystemError(msg)

    def __iter__(self) -> Iterator[type[Secret[Any]]]:
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._mapping)


class Secrets(Mapping[type[Secret[Any]], Any]):
    def __init__(self, backend: _Secrets) -> None:
        self._backend = backend

    def __contains__(self, key: object) -> bool:
        try:
            return (
                isinstance(key, type)
                and issubclass(key, Secret)
                and key in self._backend
            )
        except TypeError:
            return False

    def __getitem__[T](self, key: type[Secret[T]]) -> T:
        return self._backend[key]

    def __iter__(self) -> Iterator[type[Secret[Any]]]:
        return iter(self._backend)

    def __len__(self) -> int:
        return len(self._backend)


class DurableObjectWithSecrets(DurableObject):
    """Durable Object with built-in secret management in SQLite.

    Extends DurableObject with functionality for secure storage and management
    of secrets (API keys, tokens, etc.) in local database with validation.

    Usage:
        1. Define Secret subclasses with validation logic:

            class ApiKey(Secret[str]):
                default = "default_key"  # or Default(lambda: ...)

                @property
                def value(self) -> str:
                    return self.raw

                def validate(self, secrets: Secrets) -> str | None:
                    if len(self.raw) < 32:
                        return "Key must be at least 32 characters"
                    return None

        2. Create a DurableObjectWithSecrets subclass with registered secrets:

            class UserDO(DurableObjectWithSecrets,
                         secrets=[ApiKey, JwtSecret]):
                async def some_method(self):
                    # Access secrets via self.secrets[SecretClass]
                    api_key = self.secrets[ApiKey]  # Gets the value
                    # or raw value: self.secrets[ApiKey].raw

    Features:
        - Secrets stored in SQLite 'secret' table
        - Default values used on initialization (if set)
        - Automatic validation on creation and updates
        - RPC methods for remote secret management
        - Complex type support via Secret property methods

    Attributes:
        secret_types: Registered secret types
            (set via __init_subclass__)
        secrets: Internal _Secrets object for storage
    """

    secret_types: list[type[Secret[Any]]]

    def __init_subclass__(
        cls,
        *,
        secrets: list[type[Secret[Any]]] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init_subclass__(**kwargs)  # type: ignore[misc]
        cls.secret_types = secrets or []

    def __init__(self, ctx, env) -> None:
        self.secrets = _Secrets(Sql(ctx.storage.sql), *self.secret_types)
        super().__init__(ctx, env)

    async def get_secrets(self) -> dict[str, str]:
        """Get all registered secrets as a dictionary.

        Returns:
            Dictionary mapping secret names (lowercase class names) to their
            raw string values. Example: {"apikey": "secret_value", ...}
        """
        return self.secrets.to_dict()

    async def change_secret(self, key: str, value: str) -> str:
        """Update a secret value with validation.

        Args:
            key: Secret name (lowercase class name, e.g. "apikey")
            value: New secret value to set

        Returns:
            Empty string on success, error message on failure.
            Validation errors from the Secret class are included.
        """
        try:
            secret_cls = self.secrets.from_key(key)
            self.secrets[secret_cls] = value
        except Exception as exc:  # noqa: BLE001
            return str(exc)
        else:
            return ""
