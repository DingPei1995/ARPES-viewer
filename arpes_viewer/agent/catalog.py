"""
agent/catalog.py
================
The reference an agent reads instead of the source: ``API.md``, beside this
module -- part of the package, so it is the same file whether the program
was installed with pip or downloaded, and nothing has to be written into a
user's folders for an agent to read it.

Generated, never written by hand, from the program itself:

1. the live operations (:class:`ui.common.live.Live`: ``L.<name>(...)``), with
   their signatures and descriptions;
2. the tool-panel buttons (action name, what it takes, what it does), for
   the tools opened on screen with ``L.run_tool``;
3. the headless tools of the MCP server (route 1 without the program on
   screen);
4. the program's Qt-free computations under ``arpes_viewer.tools``, one
   line each, for computations of one's own on ``L.data(name)``.

Because it is generated, it cannot fall behind the program unnoticed: the
test ``test/agent/test_catalog.py`` regenerates it and fails when the file
differs, with the command that brings it up to date::

    python -m arpes_viewer.agent.catalog --write

Run that after every change to the operations, the tool panel, the MCP
tools or a public function under ``tools/`` (see CLAUDE.md).
"""
from __future__ import annotations

import importlib
import inspect
import os
import pkgutil
import sys

__all__ = ["live_reference", "functions_reference", "tool_actions",
           "build", "path", "main"]

#: where the reference is: beside this module, in the package (shipped as
#: package data, see pyproject.toml)
PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "API.md")


def path() -> str:
    """The reference's full path, as the system writes it."""
    return os.path.normpath(PATH)


def _doc(obj, whole: bool = True) -> str:
    text = inspect.getdoc(obj) or ""
    if not whole:
        text = text.split("\n\n")[0]
    return " ".join(text.split()) if not whole else text


def _module_summary(module) -> str:
    """A module docstring's first sentence, its file-name heading left out."""
    lines = (inspect.getdoc(module) or "").splitlines()
    if len(lines) > 1 and lines[1].strip() and set(lines[1].strip()) <= {"=", "-"}:
        lines = lines[2:]
    text = "\n".join(lines).strip().split("\n\n")[0]
    text = " ".join(text.split())
    return text.split(". ")[0].rstrip(".")[:160]


def _signature(name, function) -> str:
    signature = inspect.signature(function)
    parameters = [p for p in signature.parameters.values() if p.name != "self"]
    shown = []
    keyword_only = False
    for p in parameters:
        if p.kind is p.KEYWORD_ONLY and not keyword_only:
            shown.append("*")
            keyword_only = True
        if p.kind is p.VAR_POSITIONAL:
            shown.append(f"*{p.name}")
            keyword_only = True
            continue
        if p.kind is p.VAR_KEYWORD:
            shown.append(f"**{p.name}")
            continue
        if p.default is p.empty:
            shown.append(p.name)
        else:
            shown.append(f"{p.name}={p.default!r}")
    return f"{name}({', '.join(shown)})"


# ----------------------------------------------------------------------
# 1. the live operations
# ----------------------------------------------------------------------
def _operations():
    from arpes_viewer.ui.common.live import operations
    return operations()


def live_reference(topic: str = "") -> str:
    """The live operations as text: all of them one line each, one group
    (``topic`` a group's name) or one operation in full."""
    from arpes_viewer.ui.common.live import GROUPS
    found = _operations()
    topic = (topic or "").strip()
    if topic:
        for _group, name, method in found:
            if name == topic:
                return f"L.{_signature(name, method)}\n\n{_doc(method)}"
        group = next((g for g in GROUPS if g.lower() == topic.lower()), None)
        if group is None:
            raise KeyError(f"no operation or group {topic!r}; groups: {list(GROUPS)}")
        found = [f for f in found if f[0] == group]
    lines, current = [], None
    for group, name, method in found:
        if group != current:
            lines.append(f"\n{group}")
            current = group
        lines.append(f"  L.{_signature(name, method)}")
        lines.append(f"      {_doc(method, whole=False)}")
    return "\n".join(lines).strip()


# ----------------------------------------------------------------------
# 2. the tool-panel buttons
# ----------------------------------------------------------------------
def tool_actions() -> list:
    """``[{action, button, takes, what}]`` of every tool-panel button, in
    the panel's order."""
    from arpes_viewer.ui.launcher.list_actions import RULES
    from arpes_viewer.ui.launcher.main_window import TOOL_SECTIONS, TOOLS
    out, seen = [], set()
    for tab, sections in TOOL_SECTIONS:
        for section, actions in sections:
            for action in actions:
                if action in seen:
                    continue
                seen.add(action)
                button, what = TOOLS.get(action, (action, ""))
                takes = RULES.get(action, (None, None, ""))[2]
                out.append({"action": action, "tab": tab,
                            "section": section.replace("&&", "&"),
                            "button": button, "takes": takes,
                            "what": " ".join(what.split())})
    return out


# ----------------------------------------------------------------------
# 3. the headless MCP tools
# ----------------------------------------------------------------------
def _mcp_tools():
    from arpes_viewer.agent.server import build_server
    server = build_server()
    return [(tool.name, " ".join(tool.description.split()))
            for tool in server.tools.values()]


# ----------------------------------------------------------------------
# 4. the Qt-free computations
# ----------------------------------------------------------------------
#: the packages of computations an agent may call, in this order
FUNCTION_PACKAGES = ("spectra", "momentum", "processing", "crystal", "output")
#: modules left out: the program's own plumbing, not computations
SKIP_MODULES = {"output.colormaps", "output.figfile", "output.export",
                "crystal.last_crystal", "crystal.spacegroups",
                "spectra.corelevel_table"}


def _function_modules():
    import arpes_viewer.tools as tools
    for package in FUNCTION_PACKAGES:
        module = importlib.import_module(f"arpes_viewer.tools.{package}")
        for info in sorted(pkgutil.iter_modules(module.__path__),
                           key=lambda i: i.name):
            short = f"{package}.{info.name}"
            if short in SKIP_MODULES or info.name.startswith("_"):
                continue
            yield short, importlib.import_module(f"{tools.__name__}.{short}")


def _public_functions(module):
    names = getattr(module, "__all__", None)
    for name, member in inspect.getmembers(module, inspect.isfunction):
        if member.__module__ != module.__name__ or name.startswith("_"):
            continue
        if names is not None and name not in names:
            continue
        yield name, member


def functions_reference(module: str = "") -> str:
    """The Qt-free computations, one line each: all modules or one
    (``"spectra.peaks"``)."""
    lines = []
    for short, mod in _function_modules():
        if module and short != module:
            continue
        functions = list(_public_functions(mod))
        if not functions:
            continue
        lines.append(f"\narpes_viewer.tools.{short} -- {_module_summary(mod)}")
        for name, function in functions:
            first = _doc(function, whole=False)
            first = first.split(". ")[0].rstrip(".")
            lines.append(f"  {_signature(name, function)}")
            if first:
                lines.append(f"      {first[:200]}")
    if module and not lines:
        raise KeyError(f"no module tools.{module}")
    return "\n".join(lines).strip()


# ----------------------------------------------------------------------
# The file
# ----------------------------------------------------------------------
HEADER = """\
# ARPES viewer -- the agent's reference

*Generated from the program by `python -m arpes_viewer.agent.catalog
--write`; do not edit by hand. A test fails when it is out of date.*

Read this before anything else: it is everything the program can do, by
name, so nothing has to be found by reading the source or by pressing
buttons by their text.

## How to use it

In a command file of the live viewer (route 3) -- and in `viewer_python`,
or through the MCP tool `viewer_api` (route 1 with the program on
screen) -- **`L`** is the running program:

```python
print(L.rows())                                   # what is in the list
fit = L.fermi_edge("FS_cut", energy_window=(-0.15, 0.1), temperature=30)
cut = L.shift_energy("FS_cut", ef=fit["values"]["ef"])
k = L.cut_to_k(cut, gamma_slit_deg=0.8)            # -> a new row, its name
L.picture(k, "k", "energy", path=HERE + "/shots/cut_k.png")
L.help("kz_to_k")                                 # one operation in full
```

Rows are named, never guessed; every operation that makes data adds a new
row and records how; nothing is overwritten; no dialog waits for a click.
Results are plain dicts, lists and strings. An error says what was wrong
-- read it rather than retrying blindly.

### Which operation for which step

| Step | Operation |
|---|---|
| What is in the folder / the list | `L.add_files(folder_or_files)` (report its `left_out`, `unrecognised`, `warnings`), `L.rows(compact=True)`, `L.describe(row)`, `L.metadata(row, "photon")` |
| Look without reading the screen | `L.picture(row, x, y, path)`, `L.profile(row, along, ranges, summary=True)` |
| Fermi level, E - E_F | `L.fermi_edge_search(row)` (the candidate edges on that row's axis), `L.fermi_edge(row, window, picture=path)`, `L.shift_energy(row, ef)`; kz map: `L.kz_align_fermi(...)` |
| Clean up | `L.crop`, `L.bin`, `L.normalise` (after the Fermi fit), `L.smooth`, `L.background` |
| Second derivative, curvature, symmetrise | `L.derivative`, `L.curvature`, `L.symmetrise` |
| Dichroism, difference, ratio of two cuts | `L.cut_arithmetic(a, b, operation="asymmetry", normalise="total")` |
| To momentum | `L.cut_to_k`, `L.map_to_k` (both take `ef=` and `normalise_axes=`: one call, one row), `L.kz_to_k` (V0 from `gamma_hv`) |
| The Brillouin zone | `L.brillouin_zone`, `L.bz_overlay(row, ...)`, `L.bz3d_picture(path, ..., labels="G, L")` |
| A figure | `L.slice_series(row, values=...)`, several maps side by side: `L.slice_grid(rows, values=...)`; `L.figure_from(rows)`, `L.panel_set`, `L.panel_picture`, `L.figure_arrange`, `L.figure_describe`, `L.figure_render`, `L.figure_export`, `L.figure_save` |
| MDC/EDC fits, core levels, tight-binding, calculated bands, 3-D views ... | `L.tools()`, `L.run_tool(action, row)` (section 2) |
| Anything else | `L.data(row)` + the program's functions (section 4) + `L.add(...)` |

Where no operation fits: open the tool on screen with `L.run_tool(action,
row)` (section 2), or compute with the program's own functions (section 4)
on `L.data(row)` and list the result with `L.add(...)` -- and say that you
did.

### Working rules (learnt from real sessions)

- **Look before you compute.** Before a new kind of step, search
  `L.help()`, `L.tools()` and `L.functions()`; the program probably has it
  (dichroism is `L.cut_arithmetic`, not a formula of your own).
- **Never go around an operation silently.** Do not edit the program's
  internal tables (`A.loaded_items` ...); if no operation does it, say
  which one is missing and ask before working around it.
- **After `add_files`**, compare the rows with the folder and report what
  was left out, not recognised or warned about. Rows can be named by their
  number in `rows()` or their file's path when names are not enough.
- **Names**: say which part of a name comes from the file name and which
  from recorded metadata; mark guesses.
- **Fermi level**: on raw data, per row, on that row's own axis
  (`fermi_edge_search`); the Fermi edge is the *last* drop to the floor,
  not the steepest one. Draw each fit (`picture=`); rows of the same photon
  and pass energy must agree; when the data cannot decide, ask once.
- **A tidy list**: chain steps in one call (`map_to_k(row, ef=...,
  normalise_axes=(1, 2))`) so only the final row is listed; remove rows
  only when the person agrees.
- **Figures**: test in a `check` folder, publish one version per figure;
  signed quantities get a diverging colour map with symmetric levels.
- **Small outputs**: `rows(compact=True)`, `profile(..., summary=True)` or
  `path=`; arrays to files, not into the conversation. Code files as UTF-8,
  non-ASCII as `\\u` escapes.
- **Windows** the operations open and close never appear on screen; the
  ones left open (a figure, a tool for the person) appear on the main
  panel's screen.
"""


def build() -> str:
    """The whole reference, as written to ``API.md``."""
    parts = [HEADER]

    parts.append("## 1. Operations: `L.<name>(...)`\n")
    from arpes_viewer.ui.common.live import GROUPS
    found = _operations()
    for group in GROUPS:
        members = [(n, m) for g, n, m in found if g == group]
        if not members:
            continue
        parts.append(f"### {group}\n")
        for name, method in members:
            parts.append(f"#### `L.{_signature(name, method)}`\n")
            parts.append(_doc(method) + "\n")

    parts.append("## 2. Tool windows: `L.run_tool(action, row)`\n")
    parts.append("The tool panel's buttons, for what has no operation of its "
                 "own above. The window opens on screen, on the rows given.\n")
    parts.append("| action | button | takes | what it does |")
    parts.append("|---|---|---|---|")
    for tool in tool_actions():
        what = tool["what"].replace("|", "\\|")
        parts.append(f"| `{tool['action']}` | {tool['button']} | "
                     f"{tool['takes']} | {what} |")
    parts.append("")

    parts.append("## 3. Without the program on screen: the MCP tools\n")
    parts.append("`arpes-viewer-mcp` (route 1) offers these; the `viewer_*` "
                 "ones need the program started with `--agent-bridge`, and "
                 "`viewer_api` calls any operation of section 1.\n")
    for name, description in _mcp_tools():
        parts.append(f"- **`{name}`** -- {description}")
    parts.append("")

    parts.append("## 4. The program's computations (`arpes_viewer.tools`)\n")
    parts.append("Qt-free functions, for a computation of your own on "
                 "`L.data(row).values` / `.axes`, or in a script (route 2). "
                 "`L.functions(\"spectra.peaks\")` prints a module's "
                 "signatures and first lines; `help(function)` the whole "
                 "description.\n")
    parts.append(functions_index())
    return "\n".join(parts).rstrip() + "\n"


def functions_index() -> str:
    """Section 4 of the reference: each module, what it is for, and its
    functions' names; ``L.functions("<module>")`` gives the signatures."""
    lines = []
    for short, mod in _function_modules():
        names = [name for name, _f in _public_functions(mod)]
        if not names:
            continue
        summary = _module_summary(mod)
        lines.append(f"- **`{short}`** -- {summary}. "
                     + ", ".join(f"`{n}`" for n in names))
    return "\n".join(lines)


def main(argv=None) -> int:
    """``--write`` updates ``API.md``; ``--check`` exits 1 if it is
    out of date; no argument prints the reference."""
    argv = list(sys.argv[1:] if argv is None else argv)
    text = build()
    if "--write" in argv:
        with open(PATH, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        print(f"wrote {PATH}")
        return 0
    if "--check" in argv:
        try:
            with open(PATH, encoding="utf-8") as handle:
                current = handle.read()
        except OSError:
            current = ""
        if current != text:
            print(f"{PATH} is out of date: run "
                  f"python -m arpes_viewer.agent.catalog --write")
            return 1
        print("up to date")
        return 0
    print(text)
    return 0


if __name__ == "__main__":                                   # pragma: no cover
    raise SystemExit(main())
