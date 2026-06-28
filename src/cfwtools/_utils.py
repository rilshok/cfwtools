def to_py(obj: object) -> object:
    cast = getattr(obj, "to_py", None)
    if cast is None:
        return obj
    return to_py(cast())
