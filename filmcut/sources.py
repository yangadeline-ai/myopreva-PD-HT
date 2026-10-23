"""Load a frame shape from a scanner .OMA file, an .svg or a .plt (HPGL) file.

.OMA files are decoded with the ``omaconvert`` package
(github.com/yangadeline-ai/Converting-OMA-files). SVG and PLT files may hold
either one lens outline (the other eye is mirrored from it) or both lenses
side by side, as written by ``omaconvert --layout combined``.
"""

from __future__ import annotations

import math
import os
import re
import xml.etree.ElementTree as ET
from typing import List, Optional, Sequence, Tuple

from .geometry import (
    Polygon,
    bounds,
    box_center,
    center_on_box,
    dedupe_closed,
    ensure_ccw,
    mirror_x,
    densify,
    signed_area,
)
from .shapes import OUTLINE_POINTS, FrameShape

DEFAULT_BRIDGE = 18.0
MIN_LENS_WIDTH_MM = 10.0


class ShapeLoadError(ValueError):
    pass


# --------------------------------------------------------------------------- OMA


def load_oma_text(text: str, bridge: Optional[float] = None, name: str = "") -> FrameShape:
    try:
        from omaconvert.geometry import trace_to_xy_mm
        from omaconvert.parser import parse_oma
    except ImportError as exc:  # pragma: no cover - exercised only without the dependency
        raise ShapeLoadError(
            "Reading .OMA files needs the omaconvert package: "
            "pip install 'git+https://github.com/yangadeline-ai/Converting-OMA-files@claude/oma-to-plt-svg-converter-5rr2fd'"
        ) from exc

    oma = parse_oma(text)
    notes: List[str] = []
    outlines = {}
    for side in oma.eyes():
        pts = dedupe_closed(trace_to_xy_mm(oma.traces[side]))
        outlines[side] = center_on_box(densify(ensure_ccw(pts), OUTLINE_POINTS))

    dbl = bridge if bridge is not None else oma.dbl
    if dbl is None:
        dbl = DEFAULT_BRIDGE
        notes.append(f"OMA file has no DBL; bridge assumed {DEFAULT_BRIDGE:g} mm")

    label = name or (f"OMA job {oma.job}" if oma.job else "OMA trace")
    if len(outlines) == 1:
        (side, outline), = outlines.items()
        notes.append(f"OMA file only traces the {side} lens; the other lens is mirrored from it")
        return FrameShape.from_single(outline, side, dbl, name=label, source="oma", notes=notes)
    return FrameShape(outlines=outlines, dbl=dbl, name=label, source="oma", notes=notes)


def load_oma(path: str, bridge: Optional[float] = None) -> FrameShape:
    with open(path, "r", encoding="latin-1", newline="") as f:
        return load_oma_text(f.read(), bridge=bridge, name=os.path.basename(path))


# ------------------------------------------------------------- shared assembly


def frame_from_outlines(
    polygons: Sequence[Polygon],
    *,
    side: str = "R",
    bridge: Optional[float] = None,
    input_view: str = "front",
    name: str = "",
    source: str = "",
) -> FrameShape:
    """Pick the lens outline(s) out of a drawing and build a :class:`FrameShape`.

    Two similar-sized outlines are treated as a pair (left-most is R when
    ``input_view`` is "front", as omaconvert writes them; L when "wearer").
    A single outline is taken as lens ``side`` and mirrored for the other eye.
    """
    lenses = []
    for poly in polygons:
        poly = dedupe_closed(poly)
        if len(poly) < 3:
            continue
        x0, y0, x1, y1 = bounds(poly)
        if x1 - x0 < MIN_LENS_WIDTH_MM or y1 - y0 < MIN_LENS_WIDTH_MM / 2:
            continue
        lenses.append(poly)
    if not lenses:
        raise ShapeLoadError("No closed lens outline (at least 10 mm wide) found in the drawing")
    lenses.sort(key=lambda p: abs(signed_area(p)), reverse=True)

    if input_view == "wearer":
        lenses = [mirror_x(p) for p in lenses]

    notes: List[str] = []
    pair = len(lenses) >= 2 and abs(signed_area(lenses[1])) > 0.6 * abs(signed_area(lenses[0]))
    if pair:
        r, l = sorted(lenses[:2], key=lambda p: box_center(p)[0])
        gap = bounds(l)[0] - bounds(r)[2]
        if bridge is None:
            if gap <= 0:
                raise ShapeLoadError("The two lens outlines overlap; pass the bridge size explicitly")
            bridge = gap
        outlines = {s: center_on_box(densify(ensure_ccw(p), OUTLINE_POINTS)) for s, p in (("R", r), ("L", l))}
        if len(lenses) > 2:
            notes.append(f"{len(lenses) - 2} smaller outline(s) in the drawing were ignored")
        return FrameShape(outlines=outlines, dbl=bridge, name=name, source=source, notes=notes)

    if bridge is None:
        bridge = DEFAULT_BRIDGE
        notes.append(f"Single lens outline and no bridge given; bridge assumed {DEFAULT_BRIDGE:g} mm")
    if len(lenses) > 1:
        notes.append(f"{len(lenses) - 1} smaller outline(s) in the drawing were ignored")
    return FrameShape.from_single(lenses[0], side, bridge, name=name, source=source, notes=notes)


# --------------------------------------------------------------------------- PLT


def parse_hpgl(text: str, units_per_mm: float = 40.0) -> List[Polygon]:
    """Pen-down polylines of an HPGL file, in mm (HPGL y already points up)."""
    polys: List[Polygon] = []
    current: Polygon = []
    pos = (0.0, 0.0)
    pen_down = False
    relative = False

    def flush() -> None:
        nonlocal current
        if len(current) >= 3:
            polys.append(current)
        current = []

    for raw in re.split(r"[;\n]", text):
        cmd = raw.strip()
        if len(cmd) < 2:
            continue
        op, args = cmd[:2].upper(), cmd[2:]
        nums = [float(v) for v in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", args)]
        coords = list(zip(nums[0::2], nums[1::2]))
        if op == "PA":
            relative = False
        elif op == "PR":
            relative = True
        elif op == "PU":
            pen_down = False
            flush()
        elif op == "PD":
            if not pen_down:
                current = [pos]
            pen_down = True
        elif op == "IN":
            flush()
            pos, pen_down, relative = (0.0, 0.0), False, False
            continue
        else:
            continue
        for x, y in coords:
            pos = (pos[0] + x, pos[1] + y) if relative else (x, y)
            if pen_down:
                current.append(pos)
            elif op == "PU" or op in ("PA", "PR"):
                current = [pos]
    flush()
    return [[(x / units_per_mm, y / units_per_mm) for x, y in p] for p in polys]


def load_plt_text(text: str, units_per_mm: float = 40.0, **kw) -> FrameShape:
    return frame_from_outlines(parse_hpgl(text, units_per_mm), source="plt", **kw)


# --------------------------------------------------------------------------- SVG

Matrix = Tuple[float, float, float, float, float, float]  # a b c d e f
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _mul(m: Matrix, n: Matrix) -> Matrix:
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a * a2 + c * b2,
        b * a2 + d * b2,
        a * c2 + c * d2,
        b * c2 + d * d2,
        a * e2 + c * f2 + e,
        b * e2 + d * f2 + f,
    )


def _apply(m: Matrix, p: Tuple[float, float]) -> Tuple[float, float]:
    a, b, c, d, e, f = m
    return a * p[0] + c * p[1] + e, b * p[0] + d * p[1] + f


def _nums(s: str) -> List[float]:
    return [float(v) for v in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", s or "")]


def parse_transform(s: Optional[str]) -> Matrix:
    m = IDENTITY
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", s or ""):
        v = _nums(args)
        if name == "matrix" and len(v) == 6:
            t = tuple(v)
        elif name == "translate":
            t = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == "scale":
            t = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif name == "rotate":
            r = math.radians(v[0])
            t = (math.cos(r), math.sin(r), -math.sin(r), math.cos(r), 0, 0)
            if len(v) == 3:
                t = _mul(_mul((1, 0, 0, 1, v[1], v[2]), t), (1, 0, 0, 1, -v[1], -v[2]))
        elif name == "skewX":
            t = (1, 0, math.tan(math.radians(v[0])), 1, 0, 0)
        elif name == "skewY":
            t = (1, math.tan(math.radians(v[0])), 0, 1, 0, 0)
        else:
            continue
        m = _mul(m, tuple(float(x) for x in t))
    return m


def _bezier(points: Sequence[Tuple[float, float]], steps: int = 16) -> List[Tuple[float, float]]:
    out = []
    for i in range(1, steps + 1):
        t = i / steps
        pts = list(points)
        while len(pts) > 1:
            pts = [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for a, b in zip(pts, pts[1:])]
        out.append(pts[0])
    return out


def _arc(p0, rx, ry, phi_deg, large, sweep, p1, steps: int = 24):
    """Flatten an SVG elliptical arc (endpoint parameterisation, SVG spec F.6.5)."""
    if rx == 0 or ry == 0:
        return [p1]
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(phi_deg)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1, y1 = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = (x1 / rx) ** 2 + (y1 / ry) ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    co = math.sqrt(max(num / den, 0)) if den else 0
    if large == sweep:
        co = -co
    cx1, cy1 = co * rx * y1 / ry, -co * ry * x1 / rx
    cx = cp * cx1 - sp * cy1 + (p0[0] + p1[0]) / 2
    cy = sp * cx1 + cp * cy1 + (p0[1] + p1[1]) / 2

    def ang(u, v):
        return math.atan2(u[0] * v[1] - u[1] * v[0], u[0] * v[0] + u[1] * v[1])

    t1 = ang((1, 0), ((x1 - cx1) / rx, (y1 - cy1) / ry))
    dt = ang(((x1 - cx1) / rx, (y1 - cy1) / ry), ((-x1 - cx1) / rx, (-y1 - cy1) / ry))
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    out = []
    for i in range(1, steps + 1):
        t = t1 + dt * i / steps
        x, y = rx * math.cos(t), ry * math.sin(t)
        out.append((cp * x - sp * y + cx, sp * x + cp * y + cy))
    return out


def parse_path_d(d: str) -> List[List[Tuple[float, float]]]:
    """Flatten an SVG path ``d`` attribute into a list of subpath point lists."""
    tokens = re.findall(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", d)
    subpaths: List[List[Tuple[float, float]]] = []
    cur: List[Tuple[float, float]] = []
    pos = (0.0, 0.0)
    start = pos
    last_ctrl = None
    cmd = None
    i = 0

    def take(k):
        nonlocal i
        vals = [float(t) for t in tokens[i : i + k]]
        i += k
        return vals

    while i < len(tokens):
        if re.match(r"[A-Za-z]", tokens[i]):
            cmd = tokens[i]
            i += 1
            if cmd in "Zz":
                if cur:
                    subpaths.append(cur)
                cur = []
                pos = start
                last_ctrl = None
                continue
        if cmd is None:
            raise ShapeLoadError("SVG path data does not start with a command")
        rel = cmd.islower()
        c = cmd.upper()
        ox, oy = pos if rel else (0.0, 0.0)
        if c == "M":
            x, y = take(2)
            if cur:
                subpaths.append(cur)
            pos = (ox + x, oy + y)
            start = pos
            cur = [pos]
            cmd = "l" if rel else "L"
            last_ctrl = None
        elif c == "L":
            x, y = take(2)
            pos = (ox + x, oy + y)
            cur.append(pos)
            last_ctrl = None
        elif c == "H":
            (x,) = take(1)
            pos = ((pos[0] if rel else 0.0) + x, pos[1])
            cur.append(pos)
            last_ctrl = None
        elif c == "V":
            (y,) = take(1)
            pos = (pos[0], (pos[1] if rel else 0.0) + y)
            cur.append(pos)
            last_ctrl = None
        elif c in "CS":
            if c == "C":
                x1, y1, x2, y2, x, y = take(6)
                c1 = (ox + x1, oy + y1)
            else:
                x2, y2, x, y = take(4)
                c1 = (2 * pos[0] - last_ctrl[0], 2 * pos[1] - last_ctrl[1]) if last_ctrl else pos
            c2 = (ox + x2, oy + y2)
            end = (ox + x, oy + y)
            cur.extend(_bezier([pos, c1, c2, end]))
            last_ctrl, pos = c2, end
        elif c in "QT":
            if c == "Q":
                x1, y1, x, y = take(4)
                c1 = (ox + x1, oy + y1)
            else:
                x, y = take(2)
                c1 = (2 * pos[0] - last_ctrl[0], 2 * pos[1] - last_ctrl[1]) if last_ctrl else pos
            end = (ox + x, oy + y)
            cur.extend(_bezier([pos, c1, end]))
            last_ctrl, pos = c1, end
        elif c == "A":
            rx, ry, phi, large, sweep, x, y = take(7)
            end = (ox + x, oy + y)
            cur.extend(_arc(pos, rx, ry, phi, bool(large), bool(sweep), end))
            pos = end
            last_ctrl = None
    if cur:
        subpaths.append(cur)
    return subpaths


_UNIT_MM = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4 / 72, "pc": 25.4 / 6, "px": 25.4 / 96, "": 25.4 / 96}


def _length_mm(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    m = re.match(r"\s*([-+]?[\d.]+(?:[eE][-+]?\d+)?)\s*([a-z%]*)", value)
    if not m or m.group(2) == "%":
        return None
    return float(m.group(1)) * _UNIT_MM.get(m.group(2), 25.4 / 96)


def parse_svg(text: str) -> List[Polygon]:
    """All closed-ish shapes of an SVG, in mm with y pointing up."""
    root = ET.fromstring(text)
    vb = _nums(root.get("viewBox", ""))
    width_mm = _length_mm(root.get("width"))
    height_mm = _length_mm(root.get("height"))
    if len(vb) == 4 and width_mm:
        sx = width_mm / vb[2]
        sy = (height_mm / vb[3]) if height_mm else sx
        base: Matrix = (sx, 0, 0, sy, -vb[0] * sx, -vb[1] * sy)
    elif len(vb) == 4:
        base = (25.4 / 96, 0, 0, 25.4 / 96, -vb[0] * 25.4 / 96, -vb[1] * 25.4 / 96)
    else:
        s = 25.4 / 96
        base = (s, 0, 0, s, 0, 0)

    polys: List[Polygon] = []

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    def walk(el, m: Matrix) -> None:
        tag = local(el.tag)
        if tag in ("defs", "clipPath", "mask", "symbol", "marker", "pattern", "title", "desc"):
            return
        m = _mul(m, parse_transform(el.get("transform")))
        shapes: List[List[Tuple[float, float]]] = []
        if tag == "path":
            shapes = parse_path_d(el.get("d", ""))
        elif tag in ("polygon", "polyline"):
            v = _nums(el.get("points", ""))
            shapes = [list(zip(v[0::2], v[1::2]))]
        elif tag == "rect":
            x, y = float(el.get("x", 0)), float(el.get("y", 0))
            w, h = float(el.get("width", 0)), float(el.get("height", 0))
            shapes = [[(x, y), (x + w, y), (x + w, y + h), (x, y + h)]]
        elif tag in ("circle", "ellipse"):
            cx, cy = float(el.get("cx", 0)), float(el.get("cy", 0))
            rx = float(el.get("r", el.get("rx", 0)))
            ry = float(el.get("r", el.get("ry", 0)))
            shapes = [[(cx + rx * math.cos(t), cy + ry * math.sin(t)) for t in (2 * math.pi * k / 180 for k in range(180))]]
        for pts in shapes:
            # SVG y points down: flip to the y-up convention used everywhere else
            polys.append([(px, -py) for px, py in (_apply(m, p) for p in pts)])
        for child in el:
            walk(child, m)

    walk(root, base)
    return polys


def load_svg_text(text: str, **kw) -> FrameShape:
    polys = parse_svg(text)
    # A rect covering the whole page (e.g. omaconvert's white background) is not a lens.
    if len(polys) > 1:
        all_b = bounds([p for poly in polys for p in poly])
        polys = [p for p in polys if not (len(p) == 4 and bounds(p) == all_b)]
    return frame_from_outlines(polys, source="svg", **kw)


# ------------------------------------------------------------------- dispatcher


def load_shape_file(
    path: str,
    *,
    side: str = "R",
    bridge: Optional[float] = None,
    input_view: str = "front",
    units_per_mm: float = 40.0,
) -> FrameShape:
    ext = os.path.splitext(path)[1].lower()
    name = os.path.basename(path)
    if ext == ".oma":
        return load_oma(path, bridge=bridge)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return load_shape_text(text, ext, side=side, bridge=bridge, input_view=input_view, units_per_mm=units_per_mm, name=name)


def load_shape_text(
    text: str,
    ext: str,
    *,
    side: str = "R",
    bridge: Optional[float] = None,
    input_view: str = "front",
    units_per_mm: float = 40.0,
    name: str = "",
) -> FrameShape:
    ext = ext.lower().lstrip(".")
    if ext == "oma":
        return load_oma_text(text, bridge=bridge, name=name)
    if ext == "svg":
        return load_svg_text(text, side=side, bridge=bridge, input_view=input_view, name=name)
    if ext in ("plt", "hpgl", "hpg"):
        return load_plt_text(text, units_per_mm, side=side, bridge=bridge, input_view=input_view, name=name)
    raise ShapeLoadError(f"Unsupported shape file type {ext!r}; use .oma, .svg or .plt")
