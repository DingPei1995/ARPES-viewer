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
    """Open Slice series on `row`, fill it (timer: the dialog is modal) and make the figure; return the new FigureWindow."""
    select(row)
    before = list(app.topLevelWidgets())
    info = {}
    def fill():
        d = app.activeModalWidget()
        cb = d.findChildren(QtWidgets.QComboBox)[0]
        info["axes"] = [cb.itemText(k) for k in range(cb.count())]
        for k in range(cb.count()):
            if cb.itemText(k).startswith(axis_prefix): cb.setCurrentIndex(k)
        QtWidgets.QApplication.processEvents()
        sb = d.findChildren(QtWidgets.QSpinBox); dsb = d.findChildren(QtWidgets.QDoubleSpinBox)
        sb[0].setValue(n); sb[1].setValue(cols)
        dsb[0].setValue(start); dsb[1].setValue(stop); dsb[2].setValue(integ)
        for c in d.findChildren(QtWidgets.QCheckBox):
            if c.text().startswith("Same colour"): c.setChecked(False)
            if c.text().startswith("Title each"): c.setChecked(True)
        info["summary"] = [l.text() for l in d.findChildren(QtWidgets.QLabel) if "panel(s)" in l.text()]
        [b for b in d.findChildren(QtWidgets.QPushButton) if b.text() == "Make the figure"][0].click()
    QtCore.QTimer.singleShot(1500, fill)
    A.open_slice_series()
    pump(6)
    new = [w for w in app.topLevelWidgets() if type(w).__name__ == "FigureWindow" and all(w is not b for b in before)]
    return new[-1], info

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
    """BZ outline as UNIQUE edges: neighbouring zones share edges and drawing both made some edges look solid, others dashed."""
    seen = set(); out = []
    for px, py in polygons(ov):
        pts = list(zip(px, py)); n = len(pts)
        for k in range(n if closed else n - 1):
            a, b = pts[k], pts[(k + 1) % n]
            key = tuple(sorted([(round(a[0], 4), round(a[1], 4)), (round(b[0], 4), round(b[1], 4))]))
            if key in seen or key[0] == key[1]: continue
            seen.add(key)
            out.append(nf.Overlay(xs=[a[0], b[0]], ys=[a[1], b[1]], color=color, width_pt=width, style=style, closed=False, name=name))
    return out

def finish(fw, width_mm=180.0, rows_=3, cols_=4, big=True):
    fw.figure.match_size([1, 0], 'both')
    st = fw.figure.style
    st.width_mm = width_mm; st.gap_x_mm = 3.0; st.gap_y_mm = 4.0; st.font_pt = 8.0
    st.edge_labels_only = False
    fw.figure.arrange_grid(rows_, cols_)
    ps = fw.figure.panels
    for q in ps: q.x_labels = True; q.y_labels = True
    if big and len(ps) > 4:
        # original 3 x 4 layout kept; only the schematic (portrait) gets the free vertical space below it
        x, y, w, h = ps[0].frame
        ps[0].frame = (x, y, w, h + 14.0)
    fw.refresh()

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
FONT_PX = 48.0   # program default 14: the labels are tiny once the picture is shrunk into a 30 mm panel

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
    d.view.font_px = FONT_PX
    d.axes_box.setChecked(False)   # the tool's k_x,k_y,k_z are crystal-frame axes, not the data's k_x,k_y: do not draw them
    d.left_edit.setText(LEFT_LABELS)
    d.refresh()
    if view is not None: d.look_along(view)
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
