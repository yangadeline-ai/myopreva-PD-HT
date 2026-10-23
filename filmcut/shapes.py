"""Built-in lens shape library and the :class:`FrameShape` model.

Library shapes are stored as control points in a normalised box
(-1..1 on both axes) for the RIGHT lens seen from the front, so the nasal
side is +x. A smooth outline is drawn through them and then scaled so the
bounding box is exactly the requested A (eye size) x B (lens height).

The four traced shapes (wayfarer, square, panto, p3) follow the example
outlines in the MyoPREVA film-cutting slides.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .geometry import (
    Polygon,
    box_size,
    catmull_rom_closed,
    center_on_box,
    ensure_ccw,
    mirror_x,
    densify,
    scale_to_box,
)

OUTLINE_POINTS = 720

_CONTROL_POINTS: Dict[str, List[tuple]] = {
    "wayfarer": [
        (-0.988, 0.481), (-0.890, 0.756), (-0.675, 0.905), (-0.086, 1.0), (0.463, 0.945),
        (0.776, 0.855), (0.933, 0.705), (1.0, 0.382), (0.933, 0.082), (0.776, -0.367),
        (0.580, -0.766), (0.443, -0.915), (0.110, -0.990), (-0.282, -0.990), (-0.675, -0.890),
        (-0.890, -0.741), (-0.969, -0.466), (-1.0, 0.032),
    ],
    "square": [
        (-0.980, 0.689), (-0.827, 0.890), (-0.386, 0.977), (-0.064, 1.0), (0.418, 0.960),
        (0.819, 0.850), (0.980, 0.660), (1.0, 0.458), (0.960, 0.112), (0.859, -0.349),
        (0.739, -0.752), (0.618, -0.896), (0.217, -0.994), (-0.185, -0.983), (-0.667, -0.896),
        (-0.867, -0.695), (-0.948, -0.349), (-0.996, 0.112), (-1.0, 0.458),
    ],
    "panto": [
        (-0.988, 0.527), (-0.833, 0.796), (-0.250, 0.995), (0.177, 0.957), (0.643, 0.769),
        (0.915, 0.527), (1.0, 0.231), (0.934, -0.172), (0.759, -0.548), (0.448, -0.871),
        (0.021, -1.0), (-0.406, -0.925), (-0.717, -0.656), (-0.911, -0.280), (-1.0, 0.312),
    ],
    "p3": [
        (-0.945, 0.517), (-0.692, 0.813), (-0.017, 1.0), (0.574, 0.862), (0.911, 0.567),
        (1.0, 0.123), (0.911, -0.369), (0.574, -0.813), (-0.038, -1.0), (-0.608, -0.813),
        (-0.903, -0.419), (-1.0, 0.123),
    ],
}

# Typical B/A ratio for each shape, used when only the eye size (A) is known.
DEFAULT_ASPECT: Dict[str, float] = {
    "wayfarer": 0.786,
    "square": 0.697,
    "panto": 0.722,
    "p3": 0.857,
    "oval": 0.75,
    "rectangle": 0.60,
    "round": 1.0,
}

SHAPE_NAMES = sorted(DEFAULT_ASPECT)


def _superellipse(exponent: float, n: int = OUTLINE_POINTS) -> Polygon:
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        c, s = math.cos(t), math.sin(t)
        x = math.copysign(abs(c) ** (2.0 / exponent), c)
        y = math.copysign(abs(s) ** (2.0 / exponent), s)
        pts.append((x, y))
    return pts


def library_outline(name: str, a: float, b: Optional[float] = None) -> Polygon:
    """Right-lens (front view) outline of a built-in shape, boxed to ``a`` x ``b`` mm."""
    key = name.lower()
    if key not in DEFAULT_ASPECT:
        raise KeyError(f"Unknown shape {name!r}; choose one of {', '.join(SHAPE_NAMES)}")
    if b is None:
        b = a * DEFAULT_ASPECT[key]
    if key in _CONTROL_POINTS:
        raw = catmull_rom_closed(_CONTROL_POINTS[key])
    elif key == "rectangle":
        raw = _superellipse(5.0)
    else:  # oval / round
        raw = _superellipse(2.0)
    return scale_to_box(densify(ensure_ccw(raw), OUTLINE_POINTS), a, b)


@dataclass
class FrameShape:
    """Both lens outlines of one frame, in front view, each centred on its own box centre.

    ``outlines["R"]`` is the wearer's right lens as seen from the front (nasal
    side towards +x); ``outlines["L"]`` is the left lens (nasal side towards -x).
    """

    outlines: Dict[str, Polygon]
    dbl: float  # distance between lenses (bridge), mm
    name: str = ""
    source: str = ""
    notes: List[str] = field(default_factory=list)

    def a(self, side: str) -> float:
        return box_size(self.outlines[side])[0]

    def b(self, side: str) -> float:
        return box_size(self.outlines[side])[1]

    @property
    def frame_pd(self) -> float:
        """Boxing-system distance between lens centres: A + DBL."""
        return (self.a("R") + self.a("L")) / 2.0 + self.dbl

    @classmethod
    def from_single(cls, outline: Polygon, side: str, dbl: float, **kw) -> "FrameShape":
        """Build both lenses from one lens outline by mirroring it for the other eye."""
        own = center_on_box(densify(ensure_ccw(outline), OUTLINE_POINTS))
        other = ensure_ccw(mirror_x(own))
        if side.upper() == "R":
            outlines = {"R": own, "L": other}
        else:
            outlines = {"R": other, "L": own}
        return cls(outlines=outlines, dbl=dbl, **kw)


def library_frame(shape: str, eye: float, bridge: float, height: Optional[float] = None, name: str = "") -> FrameShape:
    """A :class:`FrameShape` from a built-in shape and the frame size printed on the temple."""
    outline = library_outline(shape, eye, height)
    return FrameShape.from_single(
        outline, "R", bridge, name=name or f"{shape} {eye:g}-{bridge:g}", source=f"library:{shape}"
    )
