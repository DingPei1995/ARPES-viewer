# r06 -- constant-energy figures + kx-cut figure with schematic panels (session of 3 Nov 2026).
# Needs r05_figure_helpers.py. Edit the PARAMETERS block, then drop this file into viewer_cmd/.
# Rules it follows: no screen reading; schematics come from the program's own 3D BZ tool (no data on them,
# axes off, high-symmetry points labelled at the left equivalents, big font); BZ drawn as unique dashed edges;
# nominal energy labels; new file names (never overwrite); .afig saved without raw data.
# ---------------- PARAMETERS ----------------
OUTDIR = DATA + r"\Report\figures"          # all outputs (set BEFORE r05 is loaded)
FINECUTS_EF = 75.344                          # eV, fitted on the RAW fine-cut map (T held): the cut axis is shifted by this
KX_CUTS = [round(-0.4 + 0.1 * i, 1) for i in range(9)]   # 1/A
exec(compile(open(HERE + r"\recipes\r05_figure_helpers.py", encoding="utf-8").read(), "r05", "exec"), globals())
# (row text in the main list, row prefix, picture file in shots\, output name)
S = HERE + r"\shots"
bz3d_tool_picture((1, 0, 0), 0.0, S + r"\b3_80LH.png")
bz3d_tool_picture((1, 0, 0), 0.0, S + r"\b3_80LV.png")
bz3d_tool_picture((1, 0, 0), 0.4465, S + r"\b3_100LH.png")
bz3d_tool_picture((0, 0, 1), 0.0, S + r"\b3_kz.png")
jobs = [
 ("hvLH [E-E_F] [kz]   [kz map (k)]", "hvLH [E-E_F] [kz]", "b3_kz.png", "Fig2_kz_constE"),
 ("FineMap80eVLH [E-E_F] [norm] [k]   [k-map]", "FineMap80eVLH [E-E_F] [norm] [k]", "b3_80LH.png", "Fig3_map80LH_constE"),
 ("FineMap80eVLV [E-E_F] [norm] [k]   [k-map]", "FineMap80eVLV [E-E_F] [norm] [k]", "b3_80LV.png", "Fig4_map80LV_constE"),
 ("FineMap100eVLH [E-E_F] [norm] [k]   [k-map]", "FineMap100eVLH [E-E_F] [norm] [k]", "b3_100LH.png", "Fig5_map100LH_constE"),
]
for row, pre, pic, name in jobs:
    try: print(name, const_energy_figure(row, pre, S + "\\" + pic, name)[0])
    except Exception:
        import traceback; print(name, "FAILED", traceback.format_exc())
    pump(4)

# --- Fig6: schematic picture of the 80 eV BZ + cuts
ROW = "FineCuts_tk [norm] [k]   [k-map]"; PRE = "FineCuts_tk [norm] [k]"
for w in top("FigureWindow"): w.close()
pump(2)
ov = bz_overlay(PRE)
polys = polygons(ov)
allx = [x for px, py in polys for x in px]; ally = [y for px, py in polys for y in py]
print("BZ extent", min(allx), max(allx), min(ally), max(ally))
xl, xh = min(allx), max(allx); yl, yh = min(ally), max(ally)
W, H = 900, 1100; ML, MR, MT, MB = 140, 40, 140, 220
FS = 80
def px_(x): return ML + (x - xl) / (xh - xl) * (W - ML - MR)
def py_(y): return H - MB - (y - yl) / (yh - yl) * (H - MT - MB)
img = QtGui.QImage(W, H, QtGui.QImage.Format_RGB32); img.fill(QtGui.QColor("white"))
qp = QtGui.QPainter(img); qp.setRenderHint(QtGui.QPainter.Antialiasing)
f = qp.font(); f.setPixelSize(FS); qp.setFont(f); fm = qp.fontMetrics()
qp.setPen(QtGui.QPen(QtGui.QColor("#e03131"), 6))
for pxs, pys in polys:
    qp.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(px_(a), py_(b)) for a, b in zip(pxs, pys)]))
kxs = KX_CUTS
qp.setPen(QtGui.QPen(QtGui.QColor("#111111"), 4, QtCore.Qt.DashLine))
for i, k in enumerate(kxs):
    qp.drawLine(QtCore.QPointF(px_(k), py_(yl)), QtCore.QPointF(px_(k), py_(yh)))
qp.setPen(QtGui.QColor("#111111"))
for i, k in enumerate(kxs):   # odd numbers above, even below: no overlap
    if i % 2 == 0: r = QtCore.QRectF(px_(k) - 40, py_(yh) - FS - 12, 80, FS + 6)
    else: r = QtCore.QRectF(px_(k) - 40, py_(yl) + 8, 80, FS + 6)
    qp.drawText(r, QtCore.Qt.AlignCenter, str(i + 1))
for name, x, y in ov["labels"]:
    if x > 1e-6 or abs(y) > 1.2: continue      # leftmost equivalent points only
    if not (xl <= x <= xh and yl <= y <= yh): continue
    tx, ty = px_(x), py_(y)
    wlab = fm.horizontalAdvance(name) + 8
    rect = QtCore.QRectF(tx - 12 - wlab, ty - FS - 4, wlab, FS + 4)
    qp.fillRect(rect, QtGui.QColor("white"))
    qp.setPen(QtGui.QColor("#e03131")); qp.drawText(rect, QtCore.Qt.AlignCenter, name)
    qp.setBrush(QtGui.QColor("#e03131")); qp.setPen(QtGui.QPen(QtGui.QColor("#e03131"), 1)); qp.drawEllipse(QtCore.QPointF(tx, ty), 7, 7)
qp.setPen(QtGui.QColor("#111111"))
qp.drawText(QtCore.QRectF(0, H - 90, W, 85), QtCore.Qt.AlignCenter, "kx (Å⁻¹)")
qp.save(); qp.translate(45, H / 2); qp.rotate(-90); qp.drawText(QtCore.QRectF(-250, -40, 500, 80), QtCore.Qt.AlignCenter, "ky (Å⁻¹)"); qp.restore()
qp.end()
SCH = S + r"\schem_cuts.png"; img.save(SCH)
fw, info = slice_figure(ROW, "along kx", -0.5, 0.4, 10, 0.02, 4)
ps = fw.figure.panels
for i, p in enumerate(ps):
    p.colormap = "blue"; p.flip = True
    if i == 0: fw.load_picture(p, SCH); p.title = ""; continue
    style_levels(p)
    k = kxs[i - 1]
    p.data.y = np.asarray(p.data.y, float) - FINECUTS_EF; p.data.y_label = "E \u2212 E_F (eV)"
    p.title = "%d: kx = %s Å⁻¹" % (i, ("%.1f" % k).replace("-", MINUS))
finish(fw, rows_=3, cols_=4)
A._fw = fw
name = "Fig6_FineCuts_kx_cuts"; files = []
for ext in ("png", "pdf"):
    files += list(fw.write(OUTDIR + "\\" + name + "." + ext, ext) or [])
fw.save_file(OUTDIR + "\\" + name + ".afig", with_data=False)
fw.grab().save(S + r"\fig_" + name + ".png")
print(files)
