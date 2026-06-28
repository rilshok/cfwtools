from collections.abc import Callable
from functools import cached_property
from typing import Any

from workers import DurableObject as _DurableObject
from workers import env

from cfwtools._utils import to_py
from cfwtools.sql import Sql


class DurableObject(_DurableObject):
    def __init__(self, ctx, env) -> None:
        super().__init__(ctx, env)
        self.__post_init__()

    @cached_property
    def name(self) -> str:
        return self.ctx.id.name

    @cached_property
    def sql(self) -> Sql:
        return Sql(self.ctx.storage.sql)

    def __post_init__(self) -> None:
        pass


def _wrap_to_py_method(method: Callable[..., Any]) -> Callable[..., Any]:
    async def wrapper(*args: object, **kwargs: object) -> object:
        result = await method(*args, **kwargs)
        return to_py(result)

    return wrapper


class _DOWrapper:
    # https://github.com/cloudflare/workers-py/issues/135
    # https://github.com/cloudflare/workers-py/pull/136

    def __init__(self, do_obj: object) -> None:
        self._do_obj = do_obj

    def __getattr__(self, name: str) -> object:
        attr = getattr(self._do_obj, name)
        if callable(attr) and not name.startswith("_"):
            return _wrap_to_py_method(attr)
        return attr


def do[DO](expected: type[DO], name: str) -> DO:
    stub = getattr(env, f"{expected.__name__}N")
    if stub is None:
        msg = f"{expected.__name__} is not bound."
        raise RuntimeError(msg)
    do_obj = stub.getByName(name)
    return _DOWrapper(do_obj)  # type: ignore
