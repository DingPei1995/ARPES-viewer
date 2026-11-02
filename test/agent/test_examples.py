"""The beginner's example scripts in agentic/examples run as published."""
import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXAMPLES = os.path.join(ROOT, "agentic", "examples")


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    from devtools import demo_data
    folder = tmp_path_factory.mktemp("demo")
    demo_data.write_all(str(folder))
    return str(folder)


def _load(name):
    sys.path.insert(0, EXAMPLES)
    try:
        spec = importlib.util.spec_from_file_location(
            name, os.path.join(EXAMPLES, name + ".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(EXAMPLES)


def test_first_look(demo, tmp_path):
    result = _load("01_first_look").main(["x", demo, str(tmp_path)])
    assert result["dataset"]["kind"] == "cut"
    assert os.path.getsize(result["png"]) > 1000 and os.path.exists(result["edc"])


def test_cut_to_momentum(demo, tmp_path):
    result = _load("02_cut_to_momentum").main(["x", demo, str(tmp_path)])
    assert [a["label"] for a in result["k"]["axes"]][1].startswith("E - E_F")
    assert os.path.exists(tmp_path / "cut_in_k.nxs")


def test_fermi_surface(demo, tmp_path):
    result = _load("03_fermi_surface").main(["x", demo, str(tmp_path)])
    assert len(result["pictures"]) == 3
    assert all(os.path.getsize(p) > 1000 for p in result["pictures"])
    assert os.path.exists(tmp_path / "k_map.nxs")
