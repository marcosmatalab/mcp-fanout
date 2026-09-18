"""Shared fixtures and the collected-test-count hook.

The hook exists because a published test count is a figure like any other, and a figure a
human has to remember to update is a figure that goes stale; rule 6 says put a command behind it.
"""

_COLLECTED: dict[str, object] = {"count": 0, "modules": set()}


def pytest_collection_modifyitems(session, config, items):
    _COLLECTED["count"] = len(items)
    _COLLECTED["modules"] = {item.path.name for item in items if hasattr(item, "path")}


def collected() -> tuple[int, set]:
    return int(_COLLECTED["count"]), set(_COLLECTED["modules"])
