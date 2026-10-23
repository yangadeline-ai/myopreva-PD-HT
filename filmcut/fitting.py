"""Place the frame's lens outlines on the film sheet so each pupil lands on a film centre.

Geometry (all mm, y up, front view unless noted)::

    frame PD           = A + DBL                (boxing centre to boxing centre)
    horizontal inset   = frame PD / 2 - monocular PD
                         (> 0: the pupil sits nasal of the lens box centre)
    vertical offset    = fitting height - frame reference height
                         (frame reference height defaults to B / 2, the box
                          centre measured up from the lowest point of the lens;
                          > 0: the pupil sits above the box centre)

The film's centre must sit on the pupil, so the lens outline is drawn on the
sheet with its box centre at  film centre - pupil offset.

Worked example from the MyoPREVA slides: frame PD 70, left PD 29 -> the
pupil is 6 mm nasal of the box centre; frame height 30, fitting height 28 ->
the pupil is 2 mm below it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .geometry import Point, Polygon, max_radius, mirror_x, offset, translate
from .shapes import FrameShape

SIDES = ("R", "L")
SIDE_NAME = {"R": "Right", "L": "Left"}


@dataclass
class FilmSheet:
    """Pre-printed MyoPREVA film sheet (defaults measured from the slides)."""

    width: float = 193.1  # 56.8 + 79.5 + 56.8
    height: float = 110.0  # 58 above the centre line + 52 below
    left_center_x: float = 56.8  # from the sheet's left edge
    center_distance: float = 79.5  # between the two film circle centres
    center_from_top: float = 58.0
    film_diameter: float = 72.0  # printed film circle
    clear_zone_diameter: float = 10.0  # small centre circle

    def centers(self) -> Tuple[Point, Point]:
        """Left and right film centres in sheet coordinates (origin top-left, y down)."""
        y = self.center_from_top
        return (self.left_center_x, y), (self.left_center_x + self.center_distance, y)


@dataclass
class Measurements:
    """Wearer measurements. Monocular PD and fitting height per eye, in mm."""

    pd_right: float
    pd_left: float
    height_right: float
    height_left: float

    def pd(self, side: str) -> float:
        return self.pd_right if side == "R" else self.pd_left

    def height(self, side: str) -> float:
        return self.height_right if side == "R" else self.height_left


@dataclass
class LensPlacement:
    side: str
    slot: str  # "left" or "right" film circle on the sheet
    film_center: Point  # sheet coords, y down
    outline: Polygon  # cut path in sheet coords, y down
    inset: float  # pupil nasal of box centre (mm)
    vertical: float  # pupil above box centre (mm)
    shift_x: float  # how far the outline moved on the sheet: + right (sheet view)
    shift_y: float  # + up
    max_radius: float  # furthest cut point from the film centre
    fits: bool


@dataclass
class Layout:
    sheet: FilmSheet
    frame: FrameShape
    measurements: Measurements
    view: str
    frame_pd: float
    frame_heights: Dict[str, float]
    placements: List[LensPlacement]
    warnings: List[str] = field(default_factory=list)

    def report(self) -> str:
        lines = [
            f"Frame: {self.frame.name or self.frame.source}",
            f"  frame PD (A + DBL) = {self.frame_pd:.2f} mm, DBL = {self.frame.dbl:.2f} mm",
            f"  view: {self.view} ({'left lens on the left of the sheet' if self.view == 'wearer' else 'right lens on the left of the sheet'})",
        ]
        for p in self.placements:
            h = "right" if p.shift_x > 0 else "left"
            v = "up" if p.shift_y > 0 else "down"
            lines.append(
                f"  {SIDE_NAME[p.side]} lens ({p.slot} film): A {self.frame.a(p.side):.2f} x B {self.frame.b(p.side):.2f} mm, "
                f"mono PD {self.measurements.pd(p.side):g}, fitting height {self.measurements.height(p.side):g} "
                f"(frame height {self.frame_heights[p.side]:.2f})"
            )
            lines.append(
                f"    pupil is {abs(p.inset):.2f} mm {'nasal' if p.inset >= 0 else 'temporal'} and "
                f"{abs(p.vertical):.2f} mm {'above' if p.vertical >= 0 else 'below'} the lens box centre; "
                f"outline moved {abs(p.shift_x):.2f} mm {h}, {abs(p.shift_y):.2f} mm {v} on the sheet; "
                f"furthest edge {p.max_radius:.1f} mm from film centre"
            )
        lines += [f"  WARNING: {w}" for w in self.warnings + self.frame.notes]
        return "\n".join(lines)


def build_layout(
    frame: FrameShape,
    measurements: Measurements,
    sheet: Optional[FilmSheet] = None,
    *,
    view: str = "wearer",
    frame_pd: Optional[float] = None,
    frame_height: Optional[float] = None,
    cut_offset: float = 0.0,
) -> Layout:
    """Position both lens outlines on the sheet.

    ``view`` is how the sheet is seen when the outlines are drawn:
    ``"wearer"`` (from behind the lenses, as the wearer sees them: left lens
    on the left film circle -- the arrangement in the MyoPREVA slides) or
    ``"front"`` (looking at the wearer, right lens on the left, as tracers
    and omaconvert draw it).

    ``frame_pd`` / ``frame_height`` override the values derived from the
    shape (A + DBL and B / 2). ``cut_offset`` grows (+) or shrinks (-) the
    cut line, e.g. -0.5 to keep the film just inside the rim.
    """
    sheet = sheet or FilmSheet()
    if view not in ("wearer", "front"):
        raise ValueError("view must be 'wearer' or 'front'")
    fpd = frame_pd if frame_pd is not None else frame.frame_pd
    left_c, right_c = sheet.centers()
    slots = {"R": ("right", right_c), "L": ("left", left_c)} if view == "wearer" else {"R": ("left", left_c), "L": ("right", right_c)}

    placements: List[LensPlacement] = []
    warnings: List[str] = []
    heights: Dict[str, float] = {}
    for side in SIDES:
        outline = frame.outlines[side]
        if cut_offset:
            outline = offset(outline, cut_offset)
        nasal = 1.0 if side == "R" else -1.0  # front view
        inset = fpd / 2.0 - measurements.pd(side)
        fh = frame_height if frame_height is not None else frame.b(side) / 2.0
        heights[side] = fh
        vertical = measurements.height(side) - fh
        pupil = (inset * nasal, vertical)
        # outline relative to the film centre (= pupil), front view, y up
        rel = translate(outline, -pupil[0], -pupil[1])
        shift = (-pupil[0], -pupil[1])
        if view == "wearer":
            rel = mirror_x(rel)
            shift = (-shift[0], shift[1])
        slot, (cx, cy) = slots[side]
        sheet_pts = [(cx + x, cy - y) for x, y in rel]
        r = max_radius(rel)
        fits = r <= sheet.film_diameter / 2.0
        if not fits:
            warnings.append(
                f"{SIDE_NAME[side]} lens outline reaches {r:.1f} mm from the film centre, "
                f"beyond the {sheet.film_diameter / 2:.1f} mm film radius"
            )
        if measurements.height(side) <= 0 or measurements.height(side) >= frame.b(side):
            warnings.append(f"{SIDE_NAME[side]} fitting height {measurements.height(side):g} mm is outside the lens (B = {frame.b(side):.1f} mm)")
        placements.append(
            LensPlacement(side, slot, (cx, cy), sheet_pts, inset, vertical, shift[0], shift[1], r, fits)
        )
    placements.sort(key=lambda p: p.slot)  # left slot first
    return Layout(sheet, frame, measurements, view, fpd, heights, placements, warnings)
