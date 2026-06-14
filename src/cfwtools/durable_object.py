from functools import cached_property
from typing import TYPE_CHECKING

from workers import DurableObject as _DurableObject

from cfwtools.sql import Sql

if TYPE_CHECKING:
    from js import DurableObjectState, Env


class DurableObject(_DurableObject):
    def __init__(self, ctx: "DurableObjectState", env: "Env") -> None:
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
