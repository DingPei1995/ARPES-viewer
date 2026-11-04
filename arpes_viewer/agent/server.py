"""
agent/server.py
===============
ARPES viewer as an MCP server: ``arpes-viewer-mcp`` (or
``python -m arpes_viewer.agent``).

Any agent that speaks the Model Context Protocol -- Claude, GPT, Gemini,
a local model through an MCP-capable client -- starts this as a subprocess
and calls its tools. Two sets:

- **Headless tools**, which need no window: find and open data files with
  the program's own loaders, describe them, read curves and pictures out of
  them, fit the Fermi edge, convert to momentum, crop, save (``.nxs`` /
  Igor), and the crystal's Brillouin zone. They run in this process.
- **viewer_* tools**, which drive the program open on screen -- when it was
  started with ``--agent-bridge`` (see :mod:`agent.bridge`): list and select
  rows, add files, run any tool-panel button, take screenshots of its
  windows, and run Python inside it.

Everything stays on the machine: the data are read and written locally,
and only what a tool returns (numbers, text, pictures) goes to the client.
"""
from __future__ import annotations

import base64
import os
import sys

from arpes_viewer.agent import bridge
from arpes_viewer.agent.protocol import Image, Server, Tool
from arpes_viewer.agent.workspace import Workspace

__all__ = ["build_server", "main", "INSTRUCTIONS"]

INSTRUCTIONS = """\
ARPES viewer: angle-resolved photoemission data on this machine.
Headless tools work on files directly: find_files -> open_dataset (gives an id
such as d1) -> describe / get_profile / get_image / fit_fermi_edge ->
convert_cut_to_k / convert_map_to_k / shift_energy / crop -> save_datasets.
Axes are named by index, slot (x, y, k, z) or a word of the label (energy,
slit, deflector, kx). Ranges are [lo, hi] in the axis's units; a single number
takes the nearest plane.
viewer_* tools drive the program on screen when it was started with
`arpes-viewer --agent-bridge`: viewer_status, viewer_rows, viewer_add_files,
viewer_select, viewer_run_tool (any tool-panel button, e.g. "fermi", "kmap",
"bz3d", "figure"), viewer_screenshot, viewer_figure, viewer_render_figure,
viewer_python. With the program on screen, viewer_api_help lists its documented
operations and viewer_api calls them (the same as L in viewer_python); use them
before anything else, and ask the person before going around them with
viewer_python (say why: name the missing operation). If your app defers tool
schemas, load every arpes-viewer tool in one search, and say what you are doing
before a long step. Keep outputs small: rows(compact=True), profile(...,
summary=True or path=...), pictures written to files. Check a figure with viewer_figure (numbers) and
viewer_render_figure (the PNG as printed) rather than a screenshot. In
viewer_python a modal dialog raises ModalDialogBlocked instead of waiting:
call the tool's function (e.g. a ContourWindow's slice_figure(values=...)). save_datasets(..., ".nxs") then viewer_add_files puts a headless
result in the on-screen list."""

_RANGES = {"type": "object",
           "description": "Ranges of the other axes to average over: "
                          "{axis: [lo, hi]} or {axis: value} (nearest "
                          "plane); axes not given are averaged whole.",
           "additionalProperties": {}}
_AXIS = {"description": "An axis: index, slot (x, y, k, z) or a word of its "
                        "label (energy, slit, kx...)."}


def _str(description):
    return {"type": "string", "description": description}


def _num(description):
    return {"type": "number", "description": description}


def _int(description):
    return {"type": "integer", "description": description}


def build_server(workspace: Workspace = None) -> Server:
    """The server with every tool, on ``workspace`` (a new one by default)."""
    from arpes_viewer.version import VERSION

    ws = workspace or Workspace()

    def get_image(id, x, y, ranges=None, colormap="gray", flip=False,
                  width=700, height=520, levels=None, gamma=1.0,
                  save_png=None, save_csv=None):
        png, summary = ws.image(id, x, y, ranges, colormap, flip, width, height,
                                levels, gamma, save_png, save_csv)
        return [summary, Image(png, f"{summary['y']} against {summary['x']}")]

    def viewer_screenshot(window="", save_png=""):
        shot = bridge.request("screenshot", window=window, path=save_png)
        png = base64.b64decode(shot.pop("png"))
        return [shot, Image(png, f"Window: {shot['title']}")]

    def viewer_render_figure(path, window="", dpi=0):
        result = bridge.request("render_figure", path=path, window=window,
                                dpi=int(dpi))
        png = base64.b64decode(result.pop("png_data"))
        return [result, Image(png, f"Figure: {result['title']}")]

    tools = [
        # -- files and datasets ------------------------------------------------
        Tool("list_loaders", "The beamline readers this program has, with the "
             "file patterns each reads.", ws.loaders, read_only=True),
        Tool("find_files", "Data files in a folder that a reader recognises, "
             "with the datasets each holds (entry, kind).",
             lambda folder, pattern="*", recursive=False, limit=300:
             ws.find_files(folder, pattern, recursive, limit),
             {"folder": _str("Folder to look in."),
              "pattern": _str("Glob, e.g. '*.nxs' (default '*')."),
              "recursive": {"type": "boolean"}, "limit": _int("At most this many.")},
             ("folder",), read_only=True),
        Tool("open_dataset", "Read one dataset (a cut, map, kz map, k-map, "
             "spatial scan, curve) with the program's loaders; returns its id "
             "and a description of its axes.",
             lambda path, entry=None, loader=None, name=None:
             ws.open(path, entry, loader, name),
             {"path": _str("File (or scan folder)."),
              "entry": _str("Which dataset of a file holding several."),
              "loader": _str("A reader's name (list_loaders), if detection "
                             "guesses wrong."),
              "name": _str("Name to give it.")}, ("path",)),
        Tool("list_datasets", "The datasets open in this session.",
             ws.listing, read_only=True),
        Tool("describe", "Kind, axes (label, range, points, step) and key "
             "metadata of a dataset.", lambda id: ws.describe(id),
             {"id": _str("Dataset id, e.g. d1.")}, ("id",), read_only=True),
        Tool("metadata", "The dataset's metadata (photon energy, temperature, "
             "analyser settings, motors...), filtered by words.",
             lambda id, contains="", limit=200: ws.metadata(id, contains, limit),
             {"id": _str("Dataset id."), "contains": _str("Words to filter by."),
              "limit": _int("At most this many fields.")}, ("id",), read_only=True),
        Tool("close_dataset", "Forget a dataset of this session.",
             lambda id: ws.close(id), {"id": _str("Dataset id.")}, ("id",)),
        # -- reading values ----------------------------------------------------
        Tool("get_profile", "A curve -- an EDC or an MDC -- along one axis, "
             "averaged over ranges of the others; numbers back as text, "
             "optionally saved as CSV.",
             lambda id, along, ranges=None, max_points=400, save_csv=None:
             ws.profile(id, along, ranges, max_points, save_csv),
             {"id": _str("Dataset id."), "along": _AXIS, "ranges": _RANGES,
              "max_points": _int("Thin the returned numbers to about this many "
                                 "(the CSV keeps all)."),
              "save_csv": _str("Write the full curve here.")},
             ("id", "along"), read_only=True),
        Tool("get_image", "A 2-D picture of the data -- a cut, a constant-"
             "energy map, a dispersion through a map -- as PNG, the other "
             "axes averaged over ranges. Optionally saved as PNG / CSV.",
             get_image,
             {"id": _str("Dataset id."), "x": _AXIS, "y": _AXIS, "ranges": _RANGES,
              "colormap": _str("A colour map name (gray, viridis, inferno, "
                               "blue...)."),
              "flip": {"type": "boolean"}, "width": _int("Pixels."),
              "height": _int("Pixels."),
              "levels": {"type": "array", "items": {"type": "number"},
                         "description": "[min, max] of the colour scale "
                                        "(default: 1st-99.5th percentile)."},
              "gamma": _num("Gamma of the colour scale."),
              "save_png": _str("Write the picture here."),
              "save_csv": _str("Write the 2-D numbers here (first row: y, "
                               "first column: x).")},
             ("id", "x", "y"), read_only=True),
        # -- analysis ------------------------------------------------------------
        Tool("fit_fermi_edge", "Fit the Fermi edge (Fermi-Dirac x linear DOS, "
             "Gaussian resolution) of the EDC averaged over ranges of the "
             "other axes: E_F, resolution, their errors.",
             lambda id, energy_window=None, temperature=30.0, ranges=None,
             fit_temperature=False: ws.fermi_edge(id, energy_window, temperature,
                                                  ranges, fit_temperature),
             {"id": _str("Dataset id."),
              "energy_window": {"type": "array", "items": {"type": "number"},
                                "description": "[lo, hi] of the fit, on the "
                                               "energy axis."},
              "temperature": _num("Sample temperature (K), held fixed unless "
                                  "fit_temperature."),
              "ranges": _RANGES, "fit_temperature": {"type": "boolean"}},
             ("id",), read_only=True),
        Tool("shift_energy", "A copy of the dataset on E - E_F, E_F given on "
             "its own energy axis (e.g. from fit_fermi_edge).",
             lambda id, ef, name=None: ws.shift_energy(id, ef, name),
             {"id": _str("Dataset id."), "ef": _num("E_F on the energy axis (eV)."),
              "name": _str("Name of the copy.")}, ("id", "ef")),
        Tool("crop", "A copy cut to ranges of its axes.",
             lambda id, ranges, name=None: ws.crop(id, ranges, name),
             {"id": _str("Dataset id."), "ranges": _RANGES, "name": _str("Name.")},
             ("id", "ranges")),
        Tool("convert_cut_to_k", "Convert a cut from angle to momentum, as the "
             "k conversion (cut) tool: Γ's slit angle, the cut's deflector "
             "angle (and Γ's, if Γ is off the cut). The energy axis must be "
             "kinetic (or the cut shifted to E - E_F by this program); "
             "output_fermi_level_eV puts the result on E - E_F.",
             lambda id, gamma_slit_deg=0.0, deflector_deg=0.0,
             gamma_deflector_deg=None, azimuth_deg=0.0, energy_offset_eV=0.0,
             output_fermi_level_eV=None, n_k=None, name=None:
             ws.convert_cut(id, gamma_slit_deg, deflector_deg, gamma_deflector_deg,
                            azimuth_deg, energy_offset_eV, output_fermi_level_eV,
                            n_k, name),
             {"id": _str("Dataset id (a cut)."),
              "gamma_slit_deg": _num("Slit angle of Γ."),
              "deflector_deg": _num("Deflector angle the cut was taken at."),
              "gamma_deflector_deg": _num("Deflector angle of Γ (default: the "
                                          "cut's, Γ on the cut)."),
              "azimuth_deg": _num("Sample rotation."),
              "energy_offset_eV": _num("Added to the energy axis first -- only "
                                       "for an axis that is not kinetic. Not "
                                       "E_F."),
              "output_fermi_level_eV": _num("E_F on the cut's energy axis: the "
                                            "result is on E - E_F."),
              "n_k": _int("Points in k."), "name": _str("Name.")}, ("id",)),
        Tool("convert_map_to_k", "Convert an angle map (deflector, slit, "
             "energy) to a k-map (kx, ky, E), as the k conversion (map) tool.",
             lambda id, gamma_deflector_deg=0.0, gamma_slit_deg=0.0,
             azimuth_deg=0.0, energy_offset_eV=0.0, output_fermi_level_eV=None,
             n_kx=None, n_ky=None, name=None:
             ws.convert_map(id, gamma_deflector_deg, gamma_slit_deg, azimuth_deg,
                            energy_offset_eV, output_fermi_level_eV, n_kx, n_ky,
                            name),
             {"id": _str("Dataset id (an angle map)."),
              "gamma_deflector_deg": _num("Deflector angle of Γ."),
              "gamma_slit_deg": _num("Slit angle of Γ."),
              "azimuth_deg": _num("Sample rotation."),
              "energy_offset_eV": _num("Only for an axis that is not kinetic. "
                                       "Not E_F."),
              "output_fermi_level_eV": _num("E_F on the map's energy axis: the "
                                            "k-map is on E - E_F."),
              "n_kx": _int("Points in kx."), "n_ky": _int("Points in ky."),
              "name": _str("Name.")}, ("id",)),
        Tool("save_datasets", "Save datasets: .nxs (this program's own -- the "
             "viewer opens it, several per file), .itx (Igor text) or .ibw "
             "(one Igor wave).",
             lambda ids, path, format=None: ws.save(ids, path, format),
             {"ids": {"type": "array", "items": {"type": "string"},
                      "description": "Dataset ids."},
              "path": _str("File to write."),
              "format": _str("nxs, itx or ibw (default: from the extension).")},
             ("ids", "path")),
        # -- the crystal --------------------------------------------------------
        Tool("brillouin_zone", "The Brillouin zone's high-symmetry points "
             "(Cartesian, Å⁻¹) and reciprocal vectors for a space group and "
             "cell; parameters the space group fixes are set by it.",
             lambda space_group, a, b=None, c=None, alpha=90.0, beta=90.0,
             gamma=None: ws.brillouin_zone(space_group, a, b, c, alpha, beta, gamma),
             {"space_group": _int("1-230."), "a": _num("Å"), "b": _num("Å"),
              "c": _num("Å"), "alpha": _num("°"), "beta": _num("°"),
              "gamma": _num("°")}, ("space_group", "a"), read_only=True),
        Tool("read_cif", "A CIF file's cell, space group and atom sites.",
             lambda path: ws.read_cif(path), {"path": _str("CIF file.")},
             ("path",), read_only=True),
        # -- the program on screen ----------------------------------------------
        Tool("viewer_status", "Whether the program is open with the agent "
             "bridge; its version, rows and open windows.",
             lambda: bridge.request("status"), read_only=True),
        Tool("viewer_rows", "The rows of the program's data list (name, kind, "
             "path, selected).", lambda: bridge.request("rows"), read_only=True),
        Tool("viewer_add_files", "Add files to the program's list (as Quick "
             "add: reader detected).",
             lambda paths: bridge.request("add_files", paths=list(paths)),
             {"paths": {"type": "array", "items": {"type": "string"}}},
             ("paths",)),
        Tool("viewer_select", "Select rows of the list by name (part of it, "
             "or exact) or number.",
             lambda names=(), rows=(), exact=False:
             bridge.request("select", names=list(names), rows=list(rows),
                            exact=bool(exact)),
             {"names": {"type": "array", "items": {"type": "string"}},
              "rows": {"type": "array", "items": {"type": "integer"}},
              "exact": {"type": "boolean"}}),
        Tool("viewer_run_tool", "Press a tool-panel button (or list button / "
             "right-click entry) for the selected rows, e.g. open, fermi, kcut, "
             "kmap, bz, bz3d, figure, slices3d, notch3d, combine, lattice, "
             "tbfit, bands. The window opens on screen; look with "
             "viewer_screenshot.",
             lambda action: bridge.request("run_tool", action=action),
             {"action": _str("The action's name.")}, ("action",)),
        Tool("viewer_windows", "The program's open windows.",
             lambda: bridge.request("windows"), read_only=True),
        Tool("viewer_screenshot", "A picture of one of the program's windows "
             "(the main window by default; else by part of its title).",
             viewer_screenshot,
             {"window": _str("Part of the window's title."),
              "save_png": _str("Also save it here.")}, read_only=True),
        Tool("viewer_api_help", "The program's documented operations "
             "(L.<name>): all of them one line each, one group, or one in "
             "full. Read this before driving the program: it replaces "
             "reading the source.",
             lambda topic="": bridge.request("api_help", topic=topic),
             {"topic": _str("An operation's or group's name (empty: all).")},
             read_only=True),
        Tool("viewer_api", "Call one documented operation of the running "
             "program on the rows of its list, e.g. operation='fermi_edge', "
             "args={'name': 'cut1', 'energy_window': [-0.15, 0.1]}. Every "
             "operation that makes data adds a new row and returns its name.",
             lambda operation, args=None: bridge.request(
                 "api", operation=operation, args=dict(args or {}), timeout=600),
             {"operation": _str("The operation's name (viewer_api_help)."),
              "args": {"type": "object",
                       "description": "Its arguments by name."}},
             ("operation",)),
        Tool("viewer_figure", "A figure window in numbers, without a "
             "picture: page size, each panel's frame (mm), title, axis names, "
             "colour scale and text sizes. Check a layout with this.",
             lambda window="": bridge.request("figure", window=window),
             {"window": _str("Part of the figure window's title (default: "
                             "the last one opened).")}, read_only=True),
        Tool("viewer_render_figure", "Write a figure window as a PNG, as it "
             "will be printed (not a screenshot), and return it with its "
             "numbers (viewer_figure).",
             viewer_render_figure,
             {"path": _str("PNG file to write (a new name each time)."),
              "window": _str("Part of the figure window's title."),
              "dpi": _int("Resolution; 0 = the figure's own.")}, ("path",)),
        Tool("viewer_close_window", "Close one of the program's windows (by "
             "part of its title).",
             lambda window: bridge.request("close_window", window=window),
             {"window": _str("Part of the window's title.")}, ("window",)),
        Tool("viewer_python", "Run Python inside the running program (globals: "
             "A = arpes_viewer.app, L = the documented operations, QtCore, "
             "QtWidgets, np, os, re, inspect, json); what it prints comes "
             "back. For anything the operations (viewer_api) do not cover; "
             "never to edit the program's internal tables -- ask the person "
             "first and name the missing operation.",
             lambda code: bridge.request("python", code=code),
             {"code": _str("Python source.")}, ("code",)),
    ]
    return Server("arpes-viewer", VERSION, tools, INSTRUCTIONS)


def main(argv=None) -> int:
    """Serve on stdin/stdout until the client goes."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # stdout carries the protocol: anything printed by a loader goes to stderr
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        build_server().serve(sys.stdin, real_stdout)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout = real_stdout
    return 0


if __name__ == "__main__":
    sys.exit(main())
