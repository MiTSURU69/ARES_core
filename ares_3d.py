"""
ares_3d.py - a real 3D Ares for the desktop companion.

No image files, no extra packages: the model is built from boxes / spheres / cylinders and drawn by a tiny
software renderer (rotate -> cull -> sort -> shade). The companion just paints the polygons it returns.

  * He turns to face the direction he walks (profile when walking sideways, back + flowing cape when walking away)
  * Real walk cycle, breathing, head look-around, cloth cape that streams behind him
  * Every mood has its own body language (listen / dictate / think / speak / happy jump-spin / error / sleep)

Model units: 1 unit ~ one old sprite pixel. Feet at y=0, crest top at y~35. +x = viewer's right, +z = towards viewer.
"""
import math

# ── palette ──────────────────────────────────────────────────────────
GOLD = (242, 194, 48)
GOLD_HI = (255, 228, 125)
GOLD_DK = (186, 128, 22)
RED = (205, 52, 43)
RED_DK = (150, 34, 34)
RED_HI = (232, 86, 66)
SKIN = (232, 160, 106)
SKIN_DK = (200, 126, 80)
STEEL = (218, 226, 234)
STEEL_DK = (150, 162, 176)
BROWN = (110, 62, 30)
VISOR = (26, 18, 24)


# ══════════════════════════════════════════════════════════════════════
#  tiny linear algebra
# ══════════════════════════════════════════════════════════════════════
def _m3(a, b):
    return (a[0] * b[0] + a[1] * b[3] + a[2] * b[6], a[0] * b[1] + a[1] * b[4] + a[2] * b[7], a[0] * b[2] + a[1] * b[5] + a[2] * b[8],
            a[3] * b[0] + a[4] * b[3] + a[5] * b[6], a[3] * b[1] + a[4] * b[4] + a[5] * b[7], a[3] * b[2] + a[4] * b[5] + a[5] * b[8],
            a[6] * b[0] + a[7] * b[3] + a[8] * b[6], a[6] * b[1] + a[7] * b[4] + a[8] * b[7], a[6] * b[2] + a[7] * b[5] + a[8] * b[8])


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return (1, 0, 0, 0, c, -s, 0, s, c)


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return (c, 0, s, 0, 1, 0, -s, 0, c)


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return (c, -s, 0, s, c, 0, 0, 0, 1)


_I3 = (1, 0, 0, 0, 1, 0, 0, 0, 1)


class Xf:
    """Rotation (3x3, flat) + translation."""
    __slots__ = ("R", "t")

    def __init__(self, R=_I3, t=(0.0, 0.0, 0.0)):
        self.R, self.t = R, t

    def apply(self, p):
        R, t = self.R, self.t
        x, y, z = p
        return (R[0] * x + R[1] * y + R[2] * z + t[0],
                R[3] * x + R[4] * y + R[5] * z + t[1],
                R[6] * x + R[7] * y + R[8] * z + t[2])

    def rot(self, n):
        R = self.R
        x, y, z = n
        return (R[0] * x + R[1] * y + R[2] * z, R[3] * x + R[4] * y + R[5] * z, R[6] * x + R[7] * y + R[8] * z)

    def __mul__(self, o):                      # (self * o)(p) = self(o(p))
        return Xf(_m3(self.R, o.R), self.apply(o.t))


def move(x, y, z):
    return Xf(_I3, (x, y, z))


def about(R, pivot):
    """Rotate by R around a pivot point."""
    px, py, pz = pivot
    x = Xf(R)
    rp = x.rot(pivot)
    return Xf(R, (px - rp[0], py - rp[1], pz - rp[2]))


# ══════════════════════════════════════════════════════════════════════
#  mesh building
# ══════════════════════════════════════════════════════════════════════
class Face:
    __slots__ = ("v", "n", "c", "shine", "two", "emit", "bias")

    def __init__(self, v, n, c, shine=0.0, two=False, emit=False, bias=0.0):
        self.v, self.n, self.c, self.shine, self.two, self.emit, self.bias = v, n, c, shine, two, emit, bias


def _norm(v):
    l = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / l, v[1] / l, v[2] / l)


def _newell(vs):
    nx = ny = nz = 0.0
    for i in range(len(vs)):
        a, b = vs[i], vs[(i + 1) % len(vs)]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return _norm((nx, ny, nz))


def _poly(vs, color, center, **kw):
    """Polygon face whose normal points away from `center`."""
    n = _newell(vs)
    fx = sum(p[0] for p in vs) / len(vs) - center[0]
    fy = sum(p[1] for p in vs) / len(vs) - center[1]
    fz = sum(p[2] for p in vs) / len(vs) - center[2]
    if n[0] * fx + n[1] * fy + n[2] * fz < 0:
        n = (-n[0], -n[1], -n[2])
    return Face(tuple(vs), n, color, **kw)


def box(cx, cy, cz, w, h, d, color, shine=0.0, bias=0.0):
    x0, x1, y0, y1, z0, z1 = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2, cz - d / 2, cz + d / 2
    F = lambda vs, n: Face(tuple(vs), n, color, shine, bias=bias)
    return [F([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], (0, 0, 1)),
            F([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)], (0, 0, -1)),
            F([(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)], (-1, 0, 0)),
            F([(x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0)], (1, 0, 0)),
            F([(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)], (0, 1, 0)),
            F([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], (0, -1, 0))]


def tbox(cx, y0, cz, wb, db, wt, dt, h, color, shine=0.0):
    """Tapered box: bottom rectangle (wb x db) at y0, top rectangle (wt x dt) at y0+h."""
    b = [(cx - wb / 2, y0, cz - db / 2), (cx + wb / 2, y0, cz - db / 2), (cx + wb / 2, y0, cz + db / 2), (cx - wb / 2, y0, cz + db / 2)]
    t = [(cx - wt / 2, y0 + h, cz - dt / 2), (cx + wt / 2, y0 + h, cz - dt / 2), (cx + wt / 2, y0 + h, cz + dt / 2), (cx - wt / 2, y0 + h, cz + dt / 2)]
    c = (cx, y0 + h / 2, cz)
    out = [_poly(b, color, c, shine=shine), _poly(t, color, c, shine=shine)]
    for i in range(4):
        j = (i + 1) % 4
        out.append(_poly([b[i], b[j], t[j], t[i]], color, c, shine=shine))
    return out


def ellipsoid(cx, cy, cz, rx, ry, rz, color, nlon=12, nlat=8, shine=0.0, lat0=-90.0, lat1=90.0, bias=0.0):
    rings = []
    for i in range(nlat + 1):
        lat = math.radians(lat0 + (lat1 - lat0) * i / nlat)
        ring = []
        for j in range(nlon):
            lon = 2 * math.pi * j / nlon
            ring.append((cx + rx * math.cos(lat) * math.sin(lon), cy + ry * math.sin(lat), cz + rz * math.cos(lat) * math.cos(lon)))
        rings.append(ring)
    out = []
    for i in range(nlat):
        for j in range(nlon):
            k = (j + 1) % nlon
            vs = [rings[i][j], rings[i][k], rings[i + 1][k], rings[i + 1][j]]
            uniq = []
            for p in vs:                                        # collapse pole duplicates
                if not uniq or max(abs(p[a] - uniq[-1][a]) for a in range(3)) > 1e-6:
                    uniq.append(p)
            if len(uniq) < 3:
                continue
            gx = sum(p[0] for p in uniq) / len(uniq) - cx
            gy = sum(p[1] for p in uniq) / len(uniq) - cy
            gz = sum(p[2] for p in uniq) / len(uniq) - cz
            n = _norm((gx / (rx * rx), gy / (ry * ry), gz / (rz * rz)))
            out.append(Face(tuple(uniq), n, color, shine, bias=bias))
    return out


def frustum_y(cx, y0, cz, rb, rt, h, color, n=10, zs=1.0, alt=None, shine=0.0, cap_top=False, cap_bot=False):
    """Vertical round tube from radius rb (bottom) to rt (top). zs squashes depth. alt = second colour for alternating panels."""
    bot, top = [], []
    for i in range(n):
        a = 2 * math.pi * i / n
        bot.append((cx + rb * math.cos(a), y0, cz + rb * zs * math.sin(a)))
        top.append((cx + rt * math.cos(a), y0 + h, cz + rt * zs * math.sin(a)))
    c = (cx, y0 + h / 2, cz)
    out = []
    for i in range(n):
        j = (i + 1) % n
        col = alt if (alt and i % 2) else color
        out.append(_poly([bot[i], bot[j], top[j], top[i]], col, c, shine=shine))
    if cap_top:
        out.append(Face(tuple(top), (0, 1, 0), color, shine))
    if cap_bot:
        out.append(Face(tuple(bot), (0, -1, 0), color, shine))
    return out


def cylinder_z(cx, cy, cz, r, length, color, n=18, shine=0.0, bias=0.0):
    """Disc / drum whose axis points at the viewer (shield)."""
    z0, z1 = cz - length / 2, cz + length / 2
    fr = [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n), z1) for i in range(n)]
    bk = [(p[0], p[1], z0) for p in fr]
    out = [Face(tuple(fr), (0, 0, 1), color, shine, bias=bias), Face(tuple(bk), (0, 0, -1), color, shine, bias=bias)]
    c = (cx, cy, cz)
    for i in range(n):
        j = (i + 1) % n
        out.append(_poly([bk[i], bk[j], fr[j], fr[i]], color, c, shine=shine, bias=bias))
    return out


def crest(cy, cz, r0, half_w=1.25):
    """Tall fan-shaped crest running front -> over the top -> down the back of the helmet."""
    angs = [72, 58, 44, 30, 16, 2, -12, -28, -44, -60, -76, -92]
    inner, outer = [], []
    for a in angs:
        ar = math.radians(a)
        hgt = max(1.2, 4.3 * (1 - abs(a - 5) / 112.0))
        for arr, rr in ((inner, r0 - 0.7), (outer, r0 + hgt)):
            arr.append((math.cos(ar) * rr, math.sin(ar) * rr))   # (up, forward)
    c = (0.0, cy, cz)
    out = []
    for i in range(len(angs) - 1):
        col = RED if i % 2 == 0 else RED_DK
        hi = RED_HI if i % 2 == 0 else RED
        a0, a1 = inner[i], inner[i + 1]
        b0, b1 = outer[i], outer[i + 1]
        P = lambda s, q: (s * half_w, cy + q[0], cz + q[1])
        out.append(_poly([P(-1, a0), P(-1, a1), P(-1, b1), P(-1, b0)], col, c))
        out.append(_poly([P(1, a0), P(1, a1), P(1, b1), P(1, b0)], col, c))
        out.append(_poly([P(-1, b0), P(1, b0), P(1, b1), P(-1, b1)], hi, c, shine=0.15))
    for idx in (0, len(angs) - 1):
        a, b = inner[idx], outer[idx]
        P = lambda s, q: (s * half_w, cy + q[0], cz + q[1])
        out.append(_poly([P(-1, a), P(1, a), P(1, b), P(-1, b)], RED_DK, c))
    return out


# ══════════════════════════════════════════════════════════════════════
#  the model, in rest pose, grouped by the joint that moves it
# ══════════════════════════════════════════════════════════════════════
HIP_Y = 12.5
SHOULDER_Y = 20.2
NECK_Y = 21.0
HEAD_CY = 26.0


def _build_leg(sx):
    th = []
    th += frustum_y(sx, 8.0, 0, 1.75, 1.95, 4.6, SKIN, n=8)                         # thigh
    th += ellipsoid(sx, 8.2, 0.9, 1.7, 1.5, 1.6, GOLD, 8, 5, shine=0.5)             # knee guard
    sh = []
    sh += frustum_y(sx, 2.0, 0, 1.6, 1.9, 6.2, GOLD, n=9, shine=0.6)                # greave
    sh += box(sx, 1.0, 0.9, 3.6, 1.4, 5.4, RED)                                     # sandal
    sh += box(sx, 0.3, 0.9, 3.8, 0.6, 5.6, RED_DK)                                  # sole
    sh += box(sx, 2.0, 0.2, 3.6, 0.6, 3.6, GOLD_DK)                                 # ankle band
    return th, sh


def _build_torso():
    f = []
    f += tbox(0, 12.5, 0, 7.6, 4.8, 9.6, 5.2, 8.5, RED)                             # tunic body
    f += box(0, 17.6, 2.7, 8.4, 6.4, 1.3, GOLD, shine=0.7)                          # breastplate
    f += box(-2.1, 19.0, 3.4, 3.6, 2.6, 0.4, GOLD_HI, shine=0.8)                    # pec highlight
    f += box(2.1, 19.0, 3.4, 3.6, 2.6, 0.4, GOLD_HI, shine=0.8)
    f += box(0, 16.0, 3.4, 0.5, 3.4, 0.3, GOLD_DK)                                  # ab line
    f += box(0, 17.6, -2.6, 8.4, 6.4, 1.2, GOLD_DK, shine=0.3)                      # back plate
    f += box(0, 13.0, 0, 9.4, 1.5, 5.8, BROWN)                                      # belt
    f += box(0, 13.0, 3.0, 1.8, 1.2, 0.5, GOLD, shine=0.8)                          # buckle
    f += frustum_y(0, 7.6, 0, 6.7, 4.9, 5.4, RED, n=12, zs=0.78, alt=RED_DK)        # pteruges skirt
    f += frustum_y(0, 7.5, 0, 6.75, 6.6, 0.7, GOLD_DK, n=12, zs=0.78)               # gold trim
    f += ellipsoid(-5.7, 20.8, 0, 2.8, 2.3, 3.0, GOLD, 10, 6, shine=0.7)            # pauldrons
    f += ellipsoid(5.7, 20.8, 0, 2.8, 2.3, 3.0, GOLD, 10, 6, shine=0.7)
    return f


def _build_arm(sx):
    up = frustum_y(sx, 15.6, 0, 1.25, 1.4, 4.8, SKIN, n=8)                          # upper arm
    fo = frustum_y(sx, 12.9, 0.3, 1.5, 1.75, 3.6, GOLD, n=8, shine=0.6)             # gauntlet
    fo += ellipsoid(sx, 12.4, 0.6, 1.4, 1.3, 1.4, SKIN_DK, 8, 5)                    # hand
    return up, fo


def _build_shield(sx):
    cx, cy, cz = sx - 1.0, 15.0, 2.6
    f = []
    f += cylinder_z(cx, cy, cz, 5.4, 1.0, GOLD_DK, shine=0.5)
    f += cylinder_z(cx, cy, cz + 0.25, 4.5, 1.1, GOLD, shine=0.8)
    f += cylinder_z(cx, cy, cz + 0.55, 2.7, 1.2, GOLD_HI, n=14, shine=0.9)
    f += cylinder_z(cx, cy, cz + 0.85, 1.35, 1.2, RED, n=12, shine=0.4)
    return f


def _build_sword(sx):
    hx, hy, hz = sx, 12.6, 1.2
    f = []
    f += box(hx, hy + 0.2, hz, 1.2, 3.0, 1.2, BROWN)                                # grip
    f += ellipsoid(hx, hy - 1.5, hz, 1.1, 0.9, 1.1, GOLD, 8, 4, shine=0.7)          # pommel
    f += box(hx, hy + 2.2, hz, 5.6, 0.9, 1.5, GOLD, shine=0.8)                      # crossguard
    f += box(hx, hy + 9.6, hz, 1.9, 13.2, 0.6, STEEL, shine=0.95)                   # blade
    f += box(hx, hy + 9.6, hz + 0.32, 0.5, 12.6, 0.15, STEEL_DK)                    # fuller
    tip = (hx, hy + 17.6, hz)
    bl = [(hx - 0.95, hy + 16.2, hz - 0.3), (hx + 0.95, hy + 16.2, hz - 0.3), (hx + 0.95, hy + 16.2, hz + 0.3), (hx - 0.95, hy + 16.2, hz + 0.3)]
    c = (hx, hy + 16.5, hz)
    for i in range(4):
        f.append(_poly([bl[i], bl[(i + 1) % 4], tip], STEEL, c, shine=0.95))
    return f


def _build_head():
    f = []
    f += ellipsoid(0, HEAD_CY, 0, 6.0, 5.6, 5.7, GOLD, 14, 8, shine=0.85, lat0=-22)  # dome
    f += box(0, 25.9, 5.15, 8.2, 3.5, 1.4, VISOR)                                    # visor slab
    f += box(0, 28.35, 5.1, 9.0, 0.9, 1.5, GOLD_HI, shine=0.9, bias=0.2)             # brow
    f += box(0, 24.35, 5.0, 8.4, 0.7, 1.4, GOLD_DK, bias=0.2)                        # visor bottom rim
    f += box(0, 25.5, 5.95, 1.05, 4.6, 0.9, GOLD, shine=0.8, bias=0.3)               # nose guard
    f += box(-3.85, 23.0, 3.2, 1.6, 5.6, 4.6, GOLD, shine=0.7)                       # cheek guards
    f += box(3.85, 23.0, 3.2, 1.6, 5.6, 4.6, GOLD, shine=0.7)
    f += box(0, 22.0, 3.7, 6.0, 3.0, 3.4, SKIN)                                      # jaw / chin
    f += box(0, 21.1, 4.9, 1.6, 0.7, 0.4, SKIN_DK, bias=0.1)                         # chin shade
    f += crest(HEAD_CY, 0.0, 5.55)
    return f


PARTS = {}


def _init_model():
    if PARTS:
        return
    PARTS["torso"] = _build_torso()
    PARTS["head"] = _build_head()
    up, fo = _build_arm(-7.2)
    PARTS["armLu"], PARTS["armLf"] = up, fo + _build_shield(-7.2)
    up, fo = _build_arm(7.2)
    PARTS["armRu"], PARTS["armRf"] = up, fo
    PARTS["sword"] = _build_sword(7.2)
    PARTS["legLt"], PARTS["legLs"] = _build_leg(-3.0)
    PARTS["legRt"], PARTS["legRs"] = _build_leg(3.0)


# ── eyes (flat glowing shapes on the visor) ──────────────────────────
def _rectp(w, h, ox=0.0, oy=0.0):
    return [(ox - w / 2, oy - h / 2), (ox + w / 2, oy - h / 2), (ox + w / 2, oy + h / 2), (ox - w / 2, oy + h / 2)]


def _rotrect(w, h, ang):
    c, s = math.cos(ang), math.sin(ang)
    return [(x * c - y * s, x * s + y * c) for x, y in _rectp(w, h)]


_CHEVRON = [(-1.4, -0.9), (0.0, 0.9), (1.4, -0.9), (0.75, -0.9), (0.0, 0.15), (-0.75, -0.9)]


def _eye_polys(kind, side):
    if kind == "blink":
        return [_rectp(1.8, 0.4, 0, -0.35)]
    if kind == "wide":
        return [_rectp(1.9, 2.7)]
    if kind == "happy":
        return [_CHEVRON]
    if kind == "think":
        return [_rectp(1.7, 1.9, 0.5, 0.5)]
    if kind == "confused":
        return [_rectp(0.9, 0.9, 0, -0.5)] if side < 0 else [_rectp(1.9, 2.7)]
    if kind == "x":
        return [_rotrect(2.6, 0.5, math.radians(45)), _rotrect(2.6, 0.5, math.radians(-45))]
    if kind == "closed":
        return [_rectp(2.4, 0.35, 0, -0.6)]
    return [_rectp(1.7, 1.9)]                                    # open


_EYE_CACHE = {}


def eye_faces(kind, rgb):
    key = (kind, rgb)
    if key in _EYE_CACHE:
        return _EYE_CACHE[key]
    faces = []
    for side in (-1, 1):
        ex, ey, ez = side * 2.45, 25.95, 5.9
        for poly in _eye_polys(kind, side):
            vs = tuple((ex + x, ey + y, ez) for x, y in poly)
            faces.append(Face(vs, (0, 0, 1), rgb, emit=True, bias=0.8))
            if kind not in ("closed", "blink") and rgb != (255, 255, 255):    # soft glow halo
                mx = sum(p[0] for p in vs) / len(vs)
                my = sum(p[1] for p in vs) / len(vs)
                hv = tuple((mx + (p[0] - mx) * 1.7, my + (p[1] - my) * 1.7, ez - 0.02) for p in vs)
                faces.append(Face(hv, (0, 0, 1), rgb + (70,), emit=True, bias=0.7))
    if len(_EYE_CACHE) > 64:
        _EYE_CACHE.clear()
    _EYE_CACHE[key] = faces
    return faces


# ══════════════════════════════════════════════════════════════════════
#  animation
# ══════════════════════════════════════════════════════════════════════
def _rest_pose():
    return dict(hop=0.0, lean=0.0, tilt=0.0, twist=0.0, hy=0.0, hp=0.0, hr=0.0,
                aLp=0.0, aLo=0.08, aRp=0.0, aRo=0.08, lL=0.0, lR=0.0, cape=1.0, crouch=0.0,
                aLy=0.0, aRy=0.0, eL=0.0, eR=0.0, B=0.0, Bw=0.0, kL=0.0, kR=0.0)


def _ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


SIDE_MOODS = {"stance", "taunt", "slash", "overhead", "thrust", "bash", "block", "parry", "hurt"}
GUARD = dict(lean=0.10, twist=-0.35, aLp=-1.2, aLo=0.05, eL=-0.45, aRp=-1.05, aRo=0.08, eR=-0.5, B=1.45,
             lL=-0.4, lR=0.35, kL=0.55, kR=0.5, hop=-1.5, cape=1.5, hy=0.0, hp=0.0)
GAITS = {  # leg swing, bounce, lean, knee bend, arm swing
    "walk": (0.78, 0.9, 0.10, 0.45, 0.55), "march": (0.85, 1.1, 0.05, 0.35, 0.5), "sneak": (0.45, 0.3, 0.22, 0.9, 0.25),
    "skip": (0.7, 1.8, 0.05, 0.5, 0.6), "run": (1.1, 1.6, 0.28, 1.25, 0.9), "guard": (0.45, 0.5, 0.12, 0.6, 0.15)}


def _wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


class Animator:
    """Holds smoothed pose + facing. Call update() every frame, then render()."""

    def __init__(self):
        self.pose = _rest_pose()
        self.yaw = 0.0
        self.spin = 0.0
        self.phase = 0.0
        self.t = 0.0
        self.mood = "idle"
        self.gt = 0.0                      # global clock for cape ripple
        self.blink_at = 2.5
        self.blink_left = 0.0
        self.walk_amt = 0.0
        self.speed = 0.0
        self.face, self.edge, self.gait = 1, False, "walk"
        self.spin_res, self.flipa = 0.0, 0.0

    # ── per frame ────────────────────────────────────────────────────
    def update(self, dt, mood, speed_units=0.0, vx=0.0, vy=0.0, gait="walk"):
        if mood != self.mood:
            self.spin_res = _wrap(self.spin + self.spin_res)     # never pop back from a half-finished spin
            self.mood, self.t = mood, 0.0
        self.gait = gait if gait in GAITS else "walk"
        self.t += dt
        self.gt += dt
        t = self.t
        walking = mood == "walk" and speed_units > 1.0
        self.speed += (speed_units - self.speed) * min(1.0, dt * 6)

        if walking:
            target = math.atan2(vx, vy * 0.9 if vy else 0.0001)
        elif mood in SIDE_MOODS:
            target = 0.75 * self.face
        else:
            target = 0.0
        self.yaw += _wrap(target - self.yaw) * min(1.0, dt * (9.0 if walking else 6.0))
        self.yaw = _wrap(self.yaw)

        self.walk_amt += ((1.0 if walking else 0.0) - self.walk_amt) * min(1.0, dt * 10)
        if walking:
            self.phase += dt * math.pi * speed_units / 11.0
        self.spin_res *= max(0.0, 1.0 - dt * 7.0)

        two_pi = 2 * math.pi
        if mood == "happy":
            self.spin = (1 - (1 - min(1.0, t / 0.85)) ** 2) * two_pi
        elif mood == "spin_slash":
            self.spin = two_pi * _ease((t - 0.12) / 0.6)
        elif mood == "twirl":
            self.spin = two_pi * (int(t / 1.15) + _ease((t % 1.15) / 1.15))
        else:
            self.spin = 0.0
        self.flipa = (two_pi if mood == "flip" else -two_pi if mood == "backflip" else 0.0) * _ease((t - 0.3) / 0.75)

        tgt = self._targets()
        rate = min(1.0, dt * 16.0)
        for k, v in tgt.items():
            self.pose[k] += (v - self.pose[k]) * rate

        if self.blink_left > 0:
            self.blink_left -= dt
        else:
            self.blink_at -= dt
            if self.blink_at <= 0:
                self.blink_left, self.blink_at = 0.13, 2.2 + (self.gt * 7.31) % 3.0

    def blinking(self) -> bool:
        return self.blink_left > 0 and self.mood in ("idle", "walk")

    def _targets(self):
        T = _rest_pose()
        m, t, ph, w = self.mood, self.t, self.phase, self.walk_amt
        g = self.gt
        br = math.sin(g * 2.3)

        # base: breathing + relaxed sway (always on, scaled down when other things are going on)
        T["hop"] = 0.18 * br
        T["hy"] = 0.28 * math.sin(g * 0.55)
        T["hr"] = 0.05 * math.sin(g * 0.8)
        T["aLo"] = 0.09 + 0.02 * br
        T["aRo"] = 0.09 + 0.02 * br
        T["aLp"] = 0.05 * math.sin(g * 1.3)
        T["aRp"] = -0.05 * math.sin(g * 1.3)

        if w > 0.02:                                                # walking blends over idle
            amp, hopk, leank, kk, armk = GAITS.get(self.gait, GAITS["walk"])
            sw = math.sin(ph)
            T["lL"] = amp * sw * w
            T["lR"] = -amp * sw * w
            T["kL"] = kk * max(0.0, math.sin(ph + 1.3)) * w
            T["kR"] = kk * max(0.0, -math.sin(ph + 1.3)) * w
            T["aLp"] = (-armk * sw) * w + T["aLp"] * (1 - w)
            T["aRp"] = (armk * sw) * w + T["aRp"] * (1 - w)
            T["hop"] = (hopk * abs(math.cos(ph))) * w + T["hop"] * (1 - w)
            T["lean"] = leank * w
            T["twist"] = 0.10 * sw * w
            T["hy"] *= (1 - w)
            if self.gait == "run":
                T["eL"] = T["eR"] = -1.3 * w
            elif self.gait == "guard":
                for k_, v_ in GUARD.items():
                    if k_ in ("aLp", "aRp", "eL", "eR", "B", "twist", "lean"):
                        T[k_] = v_ * w + T[k_] * (1 - w)
                T["Bw"] = w
                T["hop"] = -1.2 * w + T["hop"] * (1 - w)

        if m == "listen":
            T.update(hr=0.22, hp=-0.06, hy=0.0, lean=0.10, hop=0.35 * abs(math.sin(t * 9)), aRp=-0.35, aRo=0.35)
        elif m == "dictate":
            T.update(hr=0.06, hp=0.10 * math.sin(t * 7), hy=0.0, lean=0.12, hop=0.3 * abs(math.sin(t * 7)),
                     aRp=-0.55, aRo=0.25)
        elif m == "think":
            T.update(hy=0.55 * math.sin(t * 0.9 + 1.0), hp=-0.20, hr=-0.16, lean=-0.03, hop=0.15 * math.sin(t * 3),
                     aLp=-1.25, aLo=-0.05)                           # shield arm up to the chin
        elif m == "speak":
            T.update(hy=0.0, hp=0.12 * math.sin(t * 9.5), hr=0.05 * math.sin(t * 4), hop=0.55 * abs(math.sin(t * 9.5)),
                     aLp=-0.35 + 0.3 * math.sin(t * 4.5), aRp=-0.30 - 0.3 * math.sin(t * 4.5 + 1.5), aRo=0.28, aLo=0.25)
        elif m == "happy":
            T.update(hy=0.0, hp=-0.15, hop=5.5 * abs(math.sin(t * 5.2)), lean=-0.05,
                     aRp=-2.7, aRo=0.35, aLp=-0.7, aLo=0.5, lL=0.35 * math.sin(t * 10), lR=-0.35 * math.sin(t * 10))
        elif m == "error":
            T.update(hy=0.42 * math.sin(t * 24), hp=0.28, hr=0.0, lean=-0.10, twist=0.09 * math.sin(t * 19),
                     hop=0.0, aLp=0.25, aRp=0.25, aLo=0.02, aRo=0.02)
        elif m == "sleep":
            T.update(hy=0.15, hp=0.62, hr=0.18, lean=0.30, hop=-0.5 + 0.25 * math.sin(g * 1.2), aLp=0.18, aRp=0.18,
                     aLo=0.03, aRo=0.03, cape=0.4)
        elif self._extra(m, self.t, T, g):
            T["Bw"] = 1.0                                           # new poses aim the blade by absolute angle B
        return T

    def _extra(self, m, t, T, g):
        """Fight moves, dances, sitting, gestures. Returns False for moods it does not know."""
        S, PI, U, edge = math.sin, math.pi, T.update, self.edge

        def env(dur, a=0.3, b=0.35):
            return _ease(t / a) * (1 - _ease((t - (dur - b)) / b))

        def sit():
            if edge:                                                # legs dangle over a window edge, feet swinging
                s2 = S(t * 2.6)
                U(hop=-(HIP_Y - 1.3), lean=0.03, lL=-1.5, lR=-1.5, kL=1.5 + 0.45 * s2, kR=1.5 - 0.45 * s2,
                  aLp=0.25, aRp=0.25, aLo=0.25, aRo=0.25, cape=0.2)
            else:                                                   # floor: one leg folded under, other knee up
                U(hop=-(HIP_Y - 2.4) + 0.15 * S(g * 2.0), lean=-0.05, lL=-1.45, kL=2.7, lR=-1.95, kR=2.25,
                  aLp=0.45, aLo=0.4, aRp=-1.0, eR=-0.6, aRo=0.05, cape=0.2)

        if m == "sit":
            sit()
        elif m == "sit_look":
            sit(); U(hy=0.95 * S(t * 0.9), hp=-0.05)
        elif m == "sit_wave":
            sit(); U(aRp=-2.5, aRo=0.55, eR=-0.35 + 0.6 * S(t * 10), hy=0.25 * S(t * 2), hp=-0.05)
        elif m == "sit_bored":
            sit(); U(hp=0.32, hy=0.5 * S(t * 0.7), lean=0.10, aRp=-1.25, eR=-2.3)
        elif m == "sit_read":
            sit(); U(aLp=-1.15, eL=-1.4, aLo=0.1, aRp=-1.15, eR=-1.4, aRo=0.1, hp=0.55, lean=0.05)
        elif m == "meditate":
            U(hop=-(HIP_Y - 2.2) + 0.35 * S(g * 1.4), lean=0.02, hp=0.12, hy=0.0, lL=-1.3, lR=-1.3, kL=2.55, kR=2.55,
              aLp=-0.55, eL=-1.0, aLo=0.45, aRp=-0.55, eR=-1.0, aRo=0.45, cape=0.3)
        elif m == "stance":
            U(**GUARD); U(hop=GUARD["hop"] + 0.25 * S(g * 3))
        elif m == "taunt":
            U(**GUARD); U(aLp=-1.4, eL=-0.9 + 0.6 * S(t * 8), aLo=0.1, hr=0.15, lean=-0.06, twist=-0.25, tilt=0.06 * S(t * 4))
        elif m in ("slash", "overhead"):
            w, s_, r = _ease(t / 0.25), _ease((t - 0.25) / 0.13), _ease((t - 0.5) / 0.3)
            a, b_ = w * (1 - s_), s_ * (1 - r)
            U(**GUARD)
            if m == "slash":
                U(B=1.45 - 2.25 * a + 0.65 * b_, aRp=-1.05 - 0.9 * a + 0.15 * b_, eR=-0.5 - 0.3 * a,
                  twist=-0.35 - 0.5 * a + 0.9 * b_, lean=0.10 + 0.12 * b_, lL=-0.4 - 0.3 * b_)
            else:
                U(B=1.45 - 1.95 * a + 0.55 * b_, aRp=-1.05 - 1.5 * a + 0.3 * b_, eR=-0.5 - 0.2 * a,
                  lean=0.10 - 0.25 * a + 0.3 * b_, lL=-0.4 - 0.3 * b_, twist=-0.35 + 0.4 * b_)
        elif m == "thrust":
            w, s_, r = _ease(t / 0.28), _ease((t - 0.28) / 0.1), _ease((t - 0.5) / 0.3)
            a, b_ = w * (1 - s_), s_ * (1 - r)
            U(**GUARD)
            U(B=1.55, aRp=-1.05 + 0.5 * a - 0.45 * b_, eR=-0.5 - 1.2 * a + 0.45 * b_, lean=0.10 - 0.05 * a + 0.22 * b_,
              lL=-0.4 - 0.4 * b_, twist=-0.35 - 0.2 * a + 0.5 * b_)
        elif m == "bash":
            w, s_, r = _ease(t / 0.22), _ease((t - 0.22) / 0.1), _ease((t - 0.45) / 0.3)
            a, b_ = w * (1 - s_), s_ * (1 - r)
            U(**GUARD)
            U(aLp=-1.2 + 0.6 * a - 0.35 * b_, eL=-0.45 - 1.1 * a + 0.4 * b_, lean=0.10 + 0.25 * b_, lL=-0.4 - 0.4 * b_,
              twist=-0.35 + 0.3 * b_)
        elif m == "spin_slash":
            U(**GUARD); U(aRp=-1.45, eR=-0.1, B=1.55, aLp=-1.2, eL=-0.2, aLo=0.5, aRo=0.2, lean=0.1, hop=0.6, cape=3.2, twist=0.0)
        elif m == "block":
            k, rc = _ease(t / 0.08), 1 - _ease((t - 0.15) / 0.4)
            U(**GUARD); U(aLp=-1.35, eL=-1.25, aLo=-0.05, hp=0.1, lean=0.05 - 0.12 * rc * k, hop=-2.2 * k, B=1.4)
        elif m == "parry":
            sweep = S(min(1.0, t / 0.5) * PI)
            U(**GUARD); U(aRp=-1.2, eR=-0.6, B=0.3 + 1.4 * sweep, twist=-0.35 + 0.5 * sweep)
        elif m == "hurt":
            k = 1 - _ease(t / 0.55)
            U(lean=-0.38 * k, hp=-0.3 * k, hop=-0.8 - 0.6 * k, aLp=0.4 * k, aRp=0.4 * k, aLo=0.4 * k, aRo=0.4 * k, twist=0.2 * k, cape=1.8)
        elif m == "warcry":
            U(aRp=-2.6, eR=-0.15, aLp=-0.8, eL=-0.5, hp=-0.28, lean=-0.14, hop=0.6 * abs(S(t * 18)), cape=2.4)
        elif m == "victory":
            U(aRp=-2.7, eR=-0.1, aLp=-2.5, eL=-0.15, aLo=0.4, hp=-0.15, hop=2.0 * abs(S(t * 5)), lL=0.15 * S(t * 10),
              lR=-0.15 * S(t * 10), cape=2.0)
        elif m == "dance":
            b = t * 7.0
            up = max(0.0, S(b / 2)), max(0.0, -S(b / 2))
            U(hy=0.5 * S(b / 2), hp=0.05, hop=1.6 * abs(S(b)), twist=0.35 * S(b / 2), tilt=0.10 * S(b / 2 + 1.0), lean=0.04,
              aLp=-0.3 - 2.3 * up[1], aRp=-0.3 - 2.3 * up[0], aLo=0.45 + 0.3 * up[1], aRo=0.45 + 0.3 * up[0],
              lL=0.35 * S(b), lR=-0.35 * S(b), kL=0.5 * max(0.0, S(b)), kR=0.5 * max(0.0, -S(b)), eL=-0.3, eR=-0.3, cape=1.6)
        elif m == "disco":
            b = t * 5.5
            s2 = S(b)
            U(twist=0.4 * S(b / 2), hop=1.2 * abs(s2), hy=0.4 * S(b / 2), aRp=-1.6 - 1.3 * s2, aLp=-1.6 + 1.3 * s2, aRo=0.35,
              aLo=0.35, eR=-0.2, eL=-0.2, lL=0.3 * s2, lR=-0.3 * s2, cape=1.6, tilt=0.08 * S(b / 2))
        elif m == "robot":
            q = int(t * 3.4) % 4
            sgn = (1, -1, 1, -1)[q]
            U(aRp=(-1.57, -0.3, -1.57, -0.3)[q], aLp=(-0.3, -1.57, -0.3, -1.57)[q], eR=(-1.57, 0, -1.57, 0)[q],
              eL=(0, -1.57, 0, -1.57)[q], hy=0.7 * sgn, twist=0.3 * sgn, hop=0.0, aRo=0.1, aLo=0.1, cape=0.8)
        elif m == "twirl":
            U(aLp=-1.0, aRp=-1.0, aLo=0.9, aRo=0.9, hop=1.0, cape=3.0)
        elif m == "groove":
            b = t * 4.2
            U(twist=0.3 * S(b), tilt=0.1 * S(b), hop=abs(S(b)) * 1.1, aLp=-0.6 + 0.5 * S(b), aRp=-0.6 - 0.5 * S(b), eL=-0.5,
              eR=-0.5, hy=0.3 * S(b / 2), lL=0.2 * S(b), lR=-0.2 * S(b), cape=1.5)
        elif m in ("flip", "backflip"):
            air = S(PI * min(1.0, max(0.0, (t - 0.3) / 0.75)))
            pre = _ease(t / 0.28) * (1.0 if t < 0.3 else 0.0)
            U(hop=11.0 * air - 2.6 * pre, lL=0.5 * air, lR=0.5 * air, kL=1.6 * air, kR=1.6 * air, aLp=-1.4 * air, aRp=-1.4 * air, cape=2.5)
        elif m == "jump":
            air = S(PI * min(1.0, max(0.0, (t - 0.1) / 0.6)))
            U(hop=7.5 * air - 2.2 * max(0.0, 1 - t / 0.12), aLp=-2.2 * air, aRp=-2.2 * air, lL=0.35 * air, lR=0.35 * air,
              kL=0.8 * air, kR=0.8 * air, cape=2.4)
        elif m == "cheer":
            b = t * 6
            U(aRp=-2.7, eR=-0.2, aLp=-2.5, eL=-0.2, aLo=0.3, aRo=0.3, hop=1.8 * abs(S(b)), hp=-0.15, lL=0.2 * S(b), lR=-0.2 * S(b))
        elif m == "flex":
            k = _ease(t / 0.35)
            U(aLp=-0.9 * k, aLo=0.7 * k, eL=-1.9 * k, aRp=-0.9 * k, aRo=0.7 * k, eR=-1.9 * k, hop=0.6 * abs(S(t * 4)), hp=-0.1 * k, lean=-0.05 * k)
        elif m == "stretch":
            k = env(4.2, 0.8, 0.8)
            U(aLp=-2.9 * k, aRp=-2.9 * k, aLo=0.3 * k, aRo=0.3 * k, lean=-0.15 * k, hp=-0.3 * k, hop=1.2 * k, twist=0.12 * S(t * 1.6) * k)
        elif m == "yawn":
            k = env(3.2, 0.6, 0.6)
            U(hp=-0.3 * k, lean=-0.1 * k, aRp=-1.4 * k, eR=-2.0 * k, aLp=-0.4 * k, hop=0.5 * k)
        elif m == "wave":
            U(aRp=-2.45, aRo=0.55, eR=-0.35 + 0.6 * S(t * 11), hy=0.3 * S(t * 2.5), hop=0.3 * abs(S(t * 5)), aLp=-0.2)
        elif m == "salute":
            k = _ease(t / 0.25)
            U(hy=0.0, hp=-0.05, lean=-0.03, aRp=-0.85 * k, aRy=0.55 * k, eR=-1.65 * k, aRo=0.05, aLo=0.12)
        elif m == "bow":
            k = env(3.0, 0.6, 0.7)
            U(lean=0.62 * k, hp=0.22 * k, hop=-0.6 * k, aLp=0.25 * k, aRp=0.25 * k)
        elif m == "clap":
            q = abs(S(t * 13))
            U(aLp=-1.15, aRp=-1.15, eL=-0.9, eR=-0.9, aLo=-0.5 + 0.55 * q, aRo=-0.5 + 0.55 * q, hop=0.7 * q, hp=0.1)
        elif m == "laugh":
            U(hp=-0.18 + 0.16 * S(t * 18), lean=-0.08, hop=0.9 * abs(S(t * 15)), twist=0.05 * S(t * 17), aRp=-1.0, eR=-1.5, aLp=-0.4, eL=-0.6)
        elif m == "shy":
            k = env(3.4)
            U(hy=0.65 * k, hp=0.3 * k, hr=0.22 * k, twist=0.16 * k, lean=0.05 * k, aRp=-0.95 * k, eR=-1.55 * k, aLp=-0.6 * k, eL=-0.9 * k, hop=-0.3 * k)
        elif m == "confused":
            U(hr=0.32 * S(t * 2.4), hy=0.45 * S(t * 1.5), hp=-0.05, aRp=-1.35, eR=-1.75, tilt=0.05 * S(t * 2.4))
        elif m == "facepalm":
            k = _ease(t / 0.4)
            U(hp=0.38 * k, lean=0.12 * k, hop=-0.6 * k, aRp=-1.5 * k, eR=-1.7 * k, hy=0.15 * S(t * 5) * k)
        elif m == "shrug":
            k = env(2.8, 0.25, 0.4)
            U(aLp=-0.25 * k, aLo=0.75 * k, eL=-0.9 * k, aRp=-0.25 * k, aRo=0.75 * k, eR=-0.9 * k, hr=0.16 * k, hp=0.08 * k, hop=0.8 * k)
        elif m == "nod":
            U(hp=0.32 * S(t * 9), hop=0.2 * abs(S(t * 9)))
        elif m == "shake":
            U(hy=0.7 * S(t * 10))
        elif m == "awe":
            U(hp=-0.3, lean=-0.1, aLo=0.5, aRo=0.5, aLp=-0.4, aRp=-0.4, hop=0.6 + 0.6 * S(t * 3), cape=1.4)
        elif m == "shiver":
            U(twist=0.09 * S(t * 40), hop=0.25 * abs(S(t * 37)), aLp=-0.9, eL=-1.8, aRp=-0.9, eR=-1.8, aLo=-0.2, aRo=-0.2,
              lL=0.08 * S(t * 35), lR=-0.08 * S(t * 35), hp=0.1)
        elif m == "point":
            k = _ease(t / 0.3)
            U(aRp=-1.5 * k, eR=-0.05 * k, hy=-0.25 * k, B=1.5)
        elif m == "sad":
            U(hp=0.5, lean=0.13, hop=-0.7, aLp=0.12, aRp=0.12, aLo=0.03, aRo=0.03, hy=0.2 * S(t * 0.6), cape=0.5, B=3.1)
        elif m == "angry":
            U(lean=0.15, hp=0.2, hop=0.3 * abs(S(t * 22)), twist=0.06 * S(t * 25), aRp=-0.7, eR=-0.5, aLp=-0.45, eL=-0.6,
              B=0.9 + 0.15 * S(t * 20), cape=1.8)
        elif m == "heart":
            U(aRp=-1.0, eR=-1.8, aLp=-0.7, eL=-1.6, hr=0.25, hp=0.15, hop=0.5 + 0.5 * S(t * 3), twist=0.08 * S(t * 2))
        elif m == "startle":
            k = _ease(t / 0.08) * (1 - _ease((t - 0.4) / 0.5))
            U(hop=3.2 * k, lean=-0.25 * k, aLp=-0.8 * k, aRp=-0.8 * k, aLo=0.6 * k, aRo=0.6 * k, hp=-0.2 * k)
        elif m == "worry":
            U(hp=0.15, hr=0.2 * S(t * 3), hy=0.3 * S(t * 1.4), aRp=-1.25, eR=-1.7, aLp=-0.5, eL=-0.9, hop=0.25 * S(t * 6))
        elif m in ("lookaround", "sit_look2"):
            k = _ease(t / 0.4)
            U(hy=0.95 * S(t * 1.6), aRp=-1.4 * k, eR=-1.6 * k, lean=0.05)
        else:
            return False
        return True

    # ── render ───────────────────────────────────────────────────────
    def render(self, eye_kind, eye_rgb, scale, ox, oy, pitch=0.30):
        """Returns Frame. (ox, oy) = screen position of the ground point under his feet."""
        _init_model()
        P = self.pose
        yaw = self.yaw + self.spin + self.spin_res
        G = Xf(_m3(rot_x(pitch), rot_y(yaw)))

        hop = P["hop"]
        lift = move(0, hop, 0)
        R_body = _m3(rot_y(P["twist"]), _m3(rot_x(P["lean"]), rot_z(P["tilt"])))
        torso = lift * about(R_body, (0, HIP_Y, 0))
        head = torso * about(_m3(rot_y(P["hy"]), _m3(rot_x(P["hp"]), rot_z(P["hr"]))), (0, NECK_Y, 0))
        armL = torso * about(_m3(rot_y(P["aLy"]), _m3(rot_z(-P["aLo"]), rot_x(P["aLp"]))), (-5.8, SHOULDER_Y, 0))
        foreL = armL * about(rot_x(P["eL"]), (-7.2, 15.6, 0))
        armR = torso * about(_m3(rot_y(P["aRy"]), _m3(rot_z(P["aRo"]), rot_x(P["aRp"]))), (5.8, SHOULDER_Y, 0))
        foreR = armR * about(rot_x(P["eR"]), (7.2, 15.6, 0))
        swa = P["Bw"] * (P["B"] - (P["aRp"] + P["eR"]))                 # blade angle: 0 up, 1.57 forward, 3.14 down
        sword = foreR * about(rot_x(swa), (7.2, 12.6, 1.2))
        thL = lift * about(rot_x(P["lL"]), (-3.0, HIP_Y, 0))
        shL = thL * about(rot_x(P["kL"]), (-3.0, 8.1, 0))
        thR = lift * about(rot_x(P["lR"]), (3.0, HIP_Y, 0))
        shR = thR * about(rot_x(P["kR"]), (3.0, 8.1, 0))
        Gf = G * about(rot_x(self.flipa), (0, 14.0 + hop, 0)) if self.flipa else G

        jobs = [(PARTS["torso"], Gf * torso), (PARTS["head"], Gf * head), (PARTS["armLu"], Gf * armL), (PARTS["armLf"], Gf * foreL),
                (PARTS["armRu"], Gf * armR), (PARTS["armRf"], Gf * foreR), (PARTS["sword"], Gf * sword),
                (PARTS["legLt"], Gf * thL), (PARTS["legLs"], Gf * shL), (PARTS["legRt"], Gf * thR), (PARTS["legRs"], Gf * shR),
                (eye_faces(eye_kind, eye_rgb), Gf * head), (self._cape(), Gf * torso)]

        L = _norm((-0.45, 0.62, 0.65))
        H = _norm((L[0], L[1], L[2] + 1.0))
        out = []
        s = scale
        for faces, M in jobs:
            for fc in faces:
                nx, ny, nz = M.rot(fc.n)
                if nz <= 0.0:
                    if not fc.two:
                        continue
                    nx, ny, nz = -nx, -ny, -nz
                pts = [M.apply(p) for p in fc.v]
                depth = sum(p[2] for p in pts) / len(pts) + fc.bias
                if fc.emit:
                    col = fc.c
                else:
                    d = max(0.0, nx * L[0] + ny * L[1] + nz * L[2])
                    lit = 0.50 + 0.62 * d
                    r, g_, b = fc.c
                    add = 0.0
                    if fc.shine:
                        sp = max(0.0, nx * H[0] + ny * H[1] + nz * H[2])
                        add = (sp ** 18) * fc.shine * 150.0
                    col = (min(255, int(r * lit + add)), min(255, int(g_ * lit + add)), min(255, int(b * lit + add * 0.9)))
                out.append((depth, [(ox + p[0] * s, oy - p[1] * s) for p in pts], col))
        out.sort(key=lambda o: o[0])

        htop = (Gf * head).apply((0, 34.5, 0))
        crouch_shadow = min(1.0, max(0.55, 1.0 - hop * 0.06))
        return Frame([(pts, col) for _, pts, col in out],
                     (ox, oy + 0.6 * s, 7.6 * s * crouch_shadow, 2.5 * s * crouch_shadow, int(85 * crouch_shadow)),
                     (ox + htop[0] * s, oy - htop[1] * s))

    def _cape(self):
        """Cloth: 4x5 grid hanging behind the shoulders, rippling and streaming behind when he moves."""
        g, sp = self.gt, min(1.0, self.speed / 16.0)
        amp = self.pose["cape"]
        cols, rows = 4, 5
        grid = []
        for r in range(rows + 1):
            f = r / rows
            y = 20.6 - f * 12.6
            wdt = 8.4 + f * 5.0
            row = []
            for c in range(cols + 1):
                u = c / cols - 0.5
                z = -3.0 - f * 0.8 - f * f * (1.2 + 3.2 * sp) * amp
                z += math.sin(g * 3.6 + f * 2.6 + u * 2.0) * (0.35 + 0.9 * sp) * f * amp
                x = u * wdt + math.sin(g * 2.4 + f * 3.0) * 0.35 * f * amp
                row.append((x, y, z))
            grid.append(row)
        faces = []
        c0 = (0, 14.0, -1.0)
        for r in range(rows):
            for c in range(cols):
                vs = [grid[r][c], grid[r][c + 1], grid[r + 1][c + 1], grid[r + 1][c]]
                n = _newell(vs)
                if n[2] > 0:
                    n = (-n[0], -n[1], -n[2])
                col = RED_DK if (r + c) % 2 else (176, 40, 36)
                faces.append(Face(tuple(vs), n, col, 0.05, two=True, bias=-0.35))
        # gold trim along the bottom edge
        for c in range(cols):
            vs = [grid[rows][c], grid[rows][c + 1], (grid[rows][c + 1][0], grid[rows][c + 1][1] + 0.7, grid[rows][c + 1][2]),
                  (grid[rows][c][0], grid[rows][c][1] + 0.7, grid[rows][c][2])]
            n = _newell(vs)
            if n[2] > 0:
                n = (-n[0], -n[1], -n[2])
            faces.append(Face(tuple(vs), n, GOLD_DK, 0.3, two=True, bias=-0.3))
        return faces


class Frame:
    __slots__ = ("polys", "shadow", "head_top")

    def __init__(self, polys, shadow, head_top):
        self.polys, self.shadow, self.head_top = polys, shadow, head_top