"""``agentic/API.md`` is generated from the program and must match it.

When this fails, the operations, the tool panel, the MCP tools or a public
function under ``tools/`` changed without the agent's reference following.
Bring it up to date with::

    python -m arpes_viewer.agent.catalog --write
"""
import pytest

pytest.importorskip("PyQt5")


def test_the_agent_reference_is_up_to_date():
    from arpes_viewer.agent import catalog
    with open(catalog.path(), encoding="utf-8") as handle:
        current = handle.read()
    assert current == catalog.build(), (
        "agentic/API.md is out of date with the program: run "
        "python -m arpes_viewer.agent.catalog --write")


def test_every_operation_is_documented_and_grouped():
    from arpes_viewer.ui.common.live import GROUPS, operations
    found = operations()
    assert len(found) >= 40
    assert {group for group, _n, _m in found} == set(GROUPS)
    for _group, name, method in found:
        doc = (method.__doc__ or "").strip()
        assert len(doc) > 40, f"L.{name} needs a description"


def test_every_tool_button_is_in_the_reference():
    from arpes_viewer.agent import catalog
    from arpes_viewer.ui.launcher.main_window import TOOLS
    actions = {t["action"] for t in catalog.tool_actions()}
    assert set(TOOLS) <= actions
