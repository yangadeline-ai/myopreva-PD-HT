"""Small 2-D polygon helpers.

All coordinates are millimetres in standard math orientation (x to the
right, y *up*). Writers flip y where a file format needs it.
"""

from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Tuple

Point = Tuple[float, float]
Polygon = List[Point]


def bounds(points: Iterable[Point]) -> Tuple[float, float, float, float]:
    """Return (min_x, min_y, max_x, max_y)."""
    pts = list(points)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def box_center(points: Sequence[Point]) -> Point:
    """Centre of the bounding box -- the optical "boxing system" geometric centre."""
    x0, y0, x1, y1 = bounds(points)
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0


def box_size(points: Sequence[Point]) -> Tuple[float, float]:
    """(width, height) of the bounding box, i.e. boxing A and B dimensions."""
    x0, y0, x1, y1 = bounds(points)
    return x1 - x0, y1 - y0


def translate(points: Sequence[Point], dx: float, dy: float) -> Polygon:
    return [(x + dx, y + dy) for x, y in points]


def mirror_x(points: Sequence[Point]) -> Polygon:
    """Reflect across the vertical axis (x -> -x), keeping the winding direction."""
    return [(-x, y) for x, y in reversed(points)]


def center_on_box(points: Sequence[Point]) -> Polygon:
    cx, cy = box_center(points)
    return translate(points, -cx, -cy)


def scale_to_box(points: Sequence[Point], width: float, height: float) -> Polygon:
    """Scale (non-uniformly) so the bounding box is exactly width x height, centred on 0,0."""
    pts = center_on_box(points)
    w, h = box_size(pts)
    sx = width / w if w else 1.0
    sy = height / h if h else 1.0
    return [(x * sx, y * sy) for x, y in pts]


def signed_area(points: Sequence[Point]) -> float:
    """Shoelace area; positive for counter-clockwise polygons."""
    a = 0.0
    n = len(points)
    for i in range(n):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def ensure_ccw(points: Sequence[Point]) -> Polygon:
    pts = list(points)
    return pts if signed_area(pts) >= 0 else pts[::-1]


def dedupe_closed(points: Sequence[Point], eps: float = 1e-9) -> Polygon:
    """Drop consecutive duplicates and an explicit closing point equal to the first."""
    out: Polygon = []
    for p in points:
        if not out or abs(p[0] - out[-1][0]) > eps or abs(p[1] - out[-1][1]) > eps:
            out.append((float(p[0]), float(p[1])))
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) <= eps and abs(out[0][1] - out[-1][1]) <= eps:
        out.pop()
    return out


def perimeter(points: Sequence[Point]) -> float:
    n = len(points)
    return sum(math.dist(points[i], points[(i + 1) % n]) for i in range(n))


def densify(points: Sequence[Point], n: int) -> Polygon:
    """Split long edges so the outline has roughly ``n`` evenly spread points.

    Original vertices are all kept, so corners and the bounding box are exact.
    """
    pts = list(points)
    step = perimeter(pts) / max(n, 3)
    if step == 0:
        return pts
    out: Polygon = []
    for i, p in enumerate(pts):
        q = pts[(i + 1) % len(pts)]
        k = max(1, int(math.ceil(math.dist(p, q) / step - 1e-9)))
        out += [(p[0] + (q[0] - p[0]) * j / k, p[1] + (q[1] - p[1]) * j / k) for j in range(k)]
    return out


def offset(points: Sequence[Point], distance: float) -> Polygon:
    """Grow (``distance`` > 0) or shrink (< 0) a smooth closed outline.

    Each vertex moves along its averaged outward normal. That is exact for
    straight edges and accurate for the dense, smooth lens outlines this tool
    works with; it is not meant for large offsets on sharply concave shapes.
    """
    if distance == 0:
        return list(points)
    pts = ensure_ccw(points)
    n = len(pts)
    out: Polygon = []
    for i in range(n):
        px, py = pts[i - 1]
        cx, cy = pts[i]
        nx_, ny_ = pts[(i + 1) % n]
        # outward normal of a CCW edge (dx, dy) is (dy, -dx)
        e1 = (cx - px, cy - py)
        e2 = (nx_ - cx, ny_ - cy)
        l1 = math.hypot(*e1) or 1.0
        l2 = math.hypot(*e2) or 1.0
        n1 = (e1[1] / l1, -e1[0] / l1)
        n2 = (e2[1] / l2, -e2[0] / l2)
        mx, my = n1[0] + n2[0], n1[1] + n2[1]
        ml = math.hypot(mx, my)
        if ml < 1e-9:
            mx, my, ml = n2[0], n2[1], 1.0
        mx, my = mx / ml, my / ml
        # miter length so straight edges move by exactly `distance`
        cos_half = mx * n2[0] + my * n2[1]
        k = distance / max(cos_half, 0.25)
        out.append((cx + mx * k, cy + my * k))
    return out


def catmull_rom_closed(control: Sequence[Point], samples_per_segment: int = 40) -> Polygon:
    """Smooth closed curve through ``control`` points (centripetal Catmull-Rom, no overshoot)."""
    pts = list(control)
    n = len(pts)
    out: Polygon = []

    def tj(ti: float, a: Point, b: Point) -> float:
        return ti + max(math.dist(a, b), 1e-9) ** 0.5

    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        t0 = 0.0
        t1 = tj(t0, p0, p1)
        t2 = tj(t1, p1, p2)
        t3 = tj(t2, p2, p3)
        for s in range(samples_per_segment):
            t = t1 + (t2 - t1) * s / samples_per_segment

            def lerp(a: Point, b: Point, ta: float, tb: float) -> Point:
                w = (t - ta) / (tb - ta)
                return (a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w)

            a1 = lerp(p0, p1, t0, t1)
            a2 = lerp(p1, p2, t1, t2)
            a3 = lerp(p2, p3, t2, t3)
            b1 = lerp(a1, a2, t0, t2)
            b2 = lerp(a2, a3, t1, t3)
            out.append(lerp(b1, b2, t1, t2))
    return out


def max_radius(points: Sequence[Point], center: Point = (0.0, 0.0)) -> float:
    """Largest distance from ``center`` to any outline point."""
    return max(math.dist(p, center) for p in points)
