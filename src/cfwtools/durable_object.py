from functools import cached_property

from workers import DurableObject as _DurableObject

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
