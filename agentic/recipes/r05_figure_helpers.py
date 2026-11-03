import os
"""Helpers for the live viewer (route 3): slice-series figures with a 3D-BZ first panel.
Run inside a command file:  exec(compile(open(HERE + r"\\recipes\\r05_figure_helpers.py", encoding="utf-8").read(), "r05", "exec"), globals())
Uses only the program's own dialogs (Slice series, BZ overlap, figure composer); the percentile levels / gamma are our own choice.
"""
import sys, json, math, time
import numpy as np
from PyQt5 import QtGui
nf = sys.modules["arpes_viewer.tools.output.figure"]
app = QtWidgets.QApplication.instance()
L = A.ui.FilePathListWidget
MINUS = "−"

def rows():
    return [L.item(i).text() for i in range(L.count())]

def select(name):
    j = rows().index(name)
    L.clearSelection(); L.setCurrentRow(j); L.item(j).setSelected(True)

def pump(n=8, dt=0.25):
    for _ in range(n):
        QtWidgets.QApplication.processEvents(); time.sleep(dt)

def item_props(name_prefix):
    k = [x for x in A.loaded_items if str(x[1]).startswith(name_prefix)][0]
    return A.loaded_items[k]["properties"]

def bz_overlay(name_prefix):
    return json.loads(item_props(name_prefix)["bz.overlay"])

def top(cls):
    return [w for w in app.topLevelWidgets() if type(w).__name__ == cls and w.isVisible()]

def grab_bz3d(row, name_prefix, out_png, az=-60.0, el=22.0, size=(1000, 900), normal=None):
    """Grab the program's 'Cut plane in 3D' view of the dataset's stored BZ settings (BZ overlap dialog)."""
    select(row)
    mw = top("_MainWindow")[0]
    [b for b in mw.findChildren(QtWidgets.QPushButton) if b.text() == "BZ overlap..."][0].click(); pump()
    bz = top("BrillouinZoneDialog")[-1]
    if normal is not None:
        sbx = bz.findChildren(QtWidgets.QSpinBox)
        for q, val in zip(sbx[1:4], normal): q.setValue(val)
        pump(4)
    [b for b in bz.findChildren(QtWidgets.QPushButton) if b.text().startswith("Show cut plane in 3D")][0].click(); pump(12)
    v = top("CutPlanePreviewDialog")[-1]
    ps = v.findChildren(QtWidgets.QDoubleSpinBox)
    ps[0].setValue(az); ps[1].setValue(el)
    v.resize(*size); pump(10)
    desc = [l.text() for l in v.findChildren(QtWidgets.QLabel) if l.text().startswith("k_z along")]
    pw = [c for c in v.findChildren(QtWidgets.QWidget) if type(c).__name__ == "PlotWidget"][0]
    pm = pw.grab(); im = pm.toImage().convertToFormat(QtGui.QImage.Format_RGB32)
    w_, h_ = im.width(), im.height(); ptr = im.bits(); ptr.setsize(im.byteCount())
    arr = np.frombuffer(ptr, np.uint8).reshape(h_, im.bytesPerLine() // 4, 4)[:, :w_, :3].astype(int)
    mask = (np.abs(arr - arr[0, 0]) > 14).any(axis=2); ys_, xs_ = np.where(mask)
    m = 12; x0, x1 = max(xs_.min() - m, 0), min(xs_.max() + m, w_ - 1); y0, y1 = max(ys_.min() - m, 0), min(ys_.max() + m, h_ - 1)
    pm.copy(QtCore.QRect(int(x0), int(y0), int(x1 - x0 + 1), int(y1 - y0 + 1))).save(out_png)
    v.close(); bz.close(); pump(3)
    return desc

def slice_figure(row, axis_prefix, start, stop, n, integ, cols):
    """The Slice series figure of `row`, without its (modal) dialog: A.open_slice_series(values=...)
    (viewer 1.3.1). Titles carry the nominal values; the map's BZ is drawn on constant-energy panels,
    each edge once. Returns the new FigureWindow and a summary."""
    select(row)
    # the cube's axes: 0 the first (kx / deflector), 1 the second (ky / slit), 2 energy
    axis = 2 if axis_prefix.startswith("along E") else (0 if "kx" in axis_prefix else 1)
    values = list(np.linspace(start, stop, n))
    fw = A.open_slice_series(values=values, axis=axis, half_width=integ, cols=cols,
                             nominal_titles=True, zone=(axis == 2), zone_style="dashed")
    pump(4)
    return fw, {"summary": [f"{n} panel(s), +-{integ} around each"], "axes": []}

def style_levels(p, pct=(2.0, 99.5), target=0.18):
    a = np.asarray(p.data.array, float); fin = a[np.isfinite(a)]
    lo = float(np.percentile(fin, pct[0])); hi = float(np.percentile(fin, pct[1]))
    med = float(np.median(fin)); nm = min(max((med - lo) / (hi - lo), 0.05), 0.95)
    g = float(min(max(math.log(target) / math.log(nm), 0.6), 2.2))
    p.levels = (lo, hi); p.gamma = round(g, 2)
    return lo, hi, p.gamma

def polygons(ov):
    return ov["layers"]["bz_main"]["polygons"]

def bz_lines(ov, color, width, style, closed=True, name="BZ"):
    """BZ outline as UNIQUE edges (the program's tools.crystal.bz2d.unique_edges, viewer 1.3.1)."""
    from arpes_viewer.tools.crystal.bz2d import unique_edges
    return [nf.Overlay(xs=[a[0], b[0]], ys=[a[1], b[1]], color=color, width_pt=width, style=style,
                       closed=False, name=name) for a, b in unique_edges(polygons(ov))]

def finish(fw, width_mm=180.0, rows_=3, cols_=4, big=True):
    fw.figure.match_size([1, 0], 'both')
    st = fw.figure.style
    st.width_mm = width_mm; st.gap_x_mm = 3.0; st.gap_y_mm = 4.0; st.font_pt = 8.0
    st.edge_labels_only = True; st.inner_tick_numbers = True   # numbers on every panel, axis names on the edges
    ps = fw.figure.panels
    if big and len(ps) > 4:
        ps[0].span = (2, 1)          # the schematic takes two grid rows, in its own shape
    fw.figure.arrange_grid(rows_, cols_)
    fw.refresh()
    print(fw.describe())             # frames and page height in numbers (rule 17)

def crop_png(path, m=14, thr=14):
    """Crop a saved picture to its content (own helper; the program's picture has wide margins)."""
    im = QtGui.QImage(path).convertToFormat(QtGui.QImage.Format_RGB32)
    w_, h_ = im.width(), im.height(); ptr = im.bits(); ptr.setsize(im.byteCount())
    arr = np.frombuffer(ptr, np.uint8).reshape(h_, im.bytesPerLine() // 4, 4)[:, :w_, :3].astype(int)
    mask = (np.abs(arr - arr[0, 0]) > thr).any(axis=2); ys_, xs_ = np.where(mask)
    x0, x1 = max(xs_.min() - m, 0), min(xs_.max() + m, w_ - 1); y0, y1 = max(ys_.min() - m, 0), min(ys_.max() + m, h_ - 1)
    QtGui.QPixmap.fromImage(im).copy(QtCore.QRect(int(x0), int(y0), int(x1 - x0 + 1), int(y1 - y0 + 1))).save(path)
    return (int(x1 - x0 + 1), int(y1 - y0 + 1))

LEFT_LABELS = 'G, K, M, A, H, L'
PANEL_MM, TEXT_PT = 30.0, 8.0   # the schematic's width in the figure and its label size (viewer 1.3.1 sizes the labels for it)

def bz3d_tool_picture(hkl, height, out_png, map_name=None, energy=0.0, view=None):
    """The program's own '3D BZ...' window: one plane (hkl) at `height` (units of G(hkl); 0 = through Gamma), optionally carrying a k-map."""
    for w in top("BrillouinZone3DDialog"): w.close()
    pump(2)
    d = A.open_brillouin_zone_3d(); pump(6)
    r = d.plane_rows[0]
    for bx, v in zip(r.hkl_boxes, hkl): bx.setValue(v)
    r.height_box.setValue(height)
    if map_name:
        d.update_maps(); pump(3)
        i = [k for k in range(r.map_combo.count()) if r.map_combo.itemText(k) == map_name][0]
        r.map_combo.setCurrentIndex(i); r.energy_box.setValue(energy)
    d.panel_mm_box.setValue(PANEL_MM); d.text_pt_box.setValue(TEXT_PT)
    d.axes_box.setChecked(False)   # crystal axes are k_a,k_b,k_c (or d.set_frame("sample", hkl) for the data's k_x,k_y,k_z)
    d.left_edit.setText(LEFT_LABELS)
    d.refresh()
    if view is not None: d.look_along(view)   # "oblique", "k_a"..., an index 0-2 or a vector
    pump(8)
    print('left labels:', getattr(d.view, 'zone_left_labels', None))
    d.save_picture(out_png); pump(3)
    size = crop_png(out_png)
    d.close(); pump(2)
    return size

# Where figures are written. A command file may set OUTDIR before it execs this module; the default is <data_dir>\\figures.
OUTDIR = globals().get("OUTDIR") or (DATA + "\\figures")
os.makedirs(OUTDIR, exist_ok=True)

def const_energy_figure(row, prefix, picture, out_name, e_start=0.1, e_stop=-1.0, n=12, integ=0.02, extra=None):
    """12 panels: (a) 3D BZ picture, (b..) constant-energy maps 0..-1.0 eV, BZ as translucent dashed lines."""
    for w in top("FigureWindow"): w.close()
    pump(2)
    fw, info = slice_figure(row, "along E", e_start, e_stop, n, integ, 4)
    ps = fw.figure.panels; ov = bz_overlay(prefix)
    for i, p in enumerate(ps):
        p.colormap = "blue"; p.flip = True
        if i == 0:
            fw.load_picture(p, picture); p.title = ""; continue
        style_levels(p)
        p.title = "0 eV" if i == 1 else "%s%.1f eV" % (MINUS, 0.1 * (i - 1))
        p.overlays = bz_lines(ov, "#e0313199", 0.6, "dashed")
    if extra: extra(fw, ps)
    finish(fw)
    A._fw = fw
    files = []
    for ext in ("png", "pdf"):
        files += list(fw.write(OUTDIR + "\\" + out_name + "." + ext, ext) or [])
    fw.save_file(OUTDIR + "\\" + out_name + ".afig", with_data=False)
    fw.grab().save(HERE + r"\shots\fig_" + out_name + ".png")
    return info["summary"], files
