"""
ui/common/agentsteps.py
=======================
Everything an AI agent ran in the program, as one Python script.

The two routes leave their steps in different places: the command folder
(route 3) keeps every command file in ``viewer_done/`` with what it printed
in ``out/``; the agent bridge (MCP, route 1) keeps its requests in memory
only, and they are gone when the program closes. :func:`steps` reads both,
in the order they ran, and :func:`script` writes them as one file --

* a record of the whole processing, with each step's time, whether it
  failed, and what it printed (as comments);
* and a script that does it again: dropped into the command folder's
  ``viewer_cmd/`` of a running program (or passed to the MCP tool
  ``viewer_python``), it runs with ``L`` -- the documented operations --
  as every step did.

A step that failed is kept as comments: it is part of the record, and it
would only fail again.
"""
from __future__ import annotations

import os
import time

from arpes_viewer.ui.common.paths import native

__all__ = ["steps", "script", "save", "bridge_code", "default_name"]

#: how many lines of a step's printed output are kept in the script
OUTPUT_LINES = 40

#: bridge requests that are the same thing as an operation of ``L``:
#: ``op: (operation, [positional argument names], {argument: keyword})``
_AS_OPERATION = {
    "add_files": ("add_files", ["paths"], {}),
    "run_tool": ("run_tool", ["action"], {}),
    "close_window": ("close", ["window"], {}),
    "render_figure": ("figure_render", [], {"window": "title", "path": "path",
                                            "dpi": "dpi"}),
}


def _call(operation: str, positional=(), keywords=None) -> str:
    parts = [repr(value) for value in positional]
    parts += [f"{key}={value!r}" for key, value in (keywords or {}).items()]
    return f"L.{operation}({', '.join(parts)})"


def bridge_code(op: str, args: dict) -> str:
    """One request to the agent bridge as the Python that does the same
    with ``L`` (a comment, for a request that has no operation)."""
    args = dict(args or {})
    if op == "python":
        return str(args.get("code", "")).rstrip() or "pass"
    if op == "api":
        inner = dict(args.get("args") or {})
        positional = inner.pop("_args", [])
        return "print(" + _call(str(args.get("operation", "")), positional,
                                inner) + ")"
    if op == "select" and args.get("names"):
        return _call("select", list(args["names"]))
    if op in _AS_OPERATION:
        operation, order, renamed = _AS_OPERATION[op]
        positional = [args.pop(name) for name in order if name in args]
        keywords = {renamed.get(key, key): value for key, value in args.items()
                    if not renamed or key in renamed}
        return "print(" + _call(operation, positional, keywords) + ")"
    return f"# {op} {args!r}  (no operation of L does this)"


def _folder_steps(folder) -> list:
    done = os.path.join(folder.folder, "viewer_done")
    out = []
    try:
        names = [n for n in os.listdir(done) if n.endswith(".py")]
    except OSError:
        return out
    for name in names:
        path = os.path.join(done, name)
        log = os.path.join(folder.folder, "out", "cmd_" + name[:-3] + ".log")
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                code = handle.read()
        except OSError:
            continue
        try:
            with open(log, encoding="utf-8", errors="replace") as handle:
                output = handle.read()
        except OSError:
            output = ""
        try:
            stamp = os.path.getmtime(path)
        except OSError:
            stamp = 0.0
        out.append({"time": stamp, "name": name, "route": "command folder",
                    "ok": "Traceback (most recent call last)" not in output,
                    "code": code.rstrip(), "output": output.rstrip()})
    return out


def steps(app) -> list:
    """Every step the agent ran in ``app``, oldest first: dicts with
    ``time``, ``name``, ``route``, ``ok``, ``code`` and ``output``."""
    out = []
    folder = getattr(app, "_command_folder", None)
    if folder is not None:
        out += _folder_steps(folder)
    bridge = getattr(app, "_agent_bridge", None)
    for entry in list(getattr(bridge, "record", []) or []):
        detail = str((entry.get("args") or {}).get("operation", ""))
        out.append({"time": entry["time"], "route": "MCP",
                    "name": entry["op"] + (f" {detail}" if detail else ""),
                    "ok": bool(entry["ok"]),
                    "code": bridge_code(entry["op"], entry.get("args")),
                    "output": str(entry.get("result", "")).rstrip()})
    return sorted(out, key=lambda step: (step["time"], step["name"]))


def _commented(text: str, prefix: str = "# ") -> list:
    return [(prefix + line).rstrip() for line in str(text).splitlines()]


def script(app, with_output: bool = True) -> str:
    """The steps of :func:`steps` as one Python script (see the module's
    notes). ``with_output`` adds what each step printed, as comments."""
    from arpes_viewer.version import VERSION
    found = steps(app)
    folder = getattr(app, "_command_folder", None)
    here = native(getattr(folder, "folder", "") or "") or ""
    data = native(getattr(folder, "data_dir", "") or "") or ""
    failed = sum(not step["ok"] for step in found)
    lines = [
        "# -*- coding: utf-8 -*-",
        '"""',
        "The steps an AI agent ran in ARPES viewer, as one script.",
        "",
        f"Saved {time.strftime('%Y-%m-%d %H:%M')} by ARPES viewer {VERSION}.",
        f"{len(found)} step(s), oldest first"
        + (f"; {failed} failed and are kept as comments." if failed else "."),
        "",
        "To run it again: open the program's AI assistant, start it on the",
        "results folder (Copy the prompt and start), and copy this file into",
        "the command folder's viewer_cmd/ -- the program runs it and writes",
        "what it printed to out/cmd_<name>.log. An MCP app can pass it to",
        "viewer_python instead. L is the program (its operations are listed",
        "in arpes_viewer/agent/API.md, or by print(L.help())); HERE is the",
        "command folder and DATA the data folder. Every step adds new rows",
        "and files and overwrites none, so rows that are still in the list",
        "get a second copy.",
        '"""',
        "# The folders of the session this was saved from, used when the",
        "# program running the script does not give its own.",
        f"HERE = globals().get(\"HERE\") or {here!r}",
        f"DATA = globals().get(\"DATA\") or {data!r}",
    ]
    for number, step in enumerate(found, 1):
        when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(step["time"]))
        lines += ["", "",
                  f"# ---- step {number}: {step['name']}   ({step['route']}, "
                  f"{when}{'' if step['ok'] else ', FAILED'})"]
        if step["ok"]:
            lines += step["code"].splitlines()
        else:
            lines += ["# It failed when it ran; kept for the record:"]
            lines += _commented(step["code"], "#     ")
        if with_output and step["output"]:
            printed = step["output"].splitlines()
            lines.append("# It printed:")
            lines += _commented("\n".join(printed[:OUTPUT_LINES]), "#   ")
            if len(printed) > OUTPUT_LINES:
                lines.append(f"#   ... ({len(printed) - OUTPUT_LINES} more "
                             f"line(s))")
    return "\n".join(lines) + "\n"


def default_name() -> str:
    return time.strftime("agent_steps_%Y%m%d_%H%M.py")


def save(app, path: str, with_output: bool = True) -> dict:
    """Write :func:`script` to ``path``; returns ``{"path", "steps",
    "failed"}``."""
    path = os.path.normpath(os.path.expanduser(path))
    found = steps(app)
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(script(app, with_output=with_output))
    return {"path": path, "steps": len(found),
            "failed": sum(not step["ok"] for step in found)}
