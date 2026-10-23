"""Write a :class:`~filmcut.fitting.Layout` as cutter files.

- ``cut.svg``     only the two cut lines, sheet-sized, in mm (Silhouette Studio
                  Designer Edition, Cricut, Inkscape, LightBurn ...)
- ``preview.svg`` the sheet with film circles, centre marks and the cut lines,
                  for checking by eye -- not for cutting
- ``.dxf``        R12 polylines in mm (Silhouette Studio Basic Edition opens DXF)
- ``.plt``        HPGL for plotter-style cutters (Graphtec, Roland, ...)

Every file uses the whole sheet as its page with the origin at the sheet's
corner, so a sheet loaded square against the cutter's origin cuts in place.
"""

from __future__ import annotations

from typing import List
from xml.sax.saxutils import escape

from .fitting import SIDE_NAME, Layout
from .geometry import Polygon

CUT_COLOR = "#ff0000"
EYE_COLOR = {"R": "#b2182b", "L": "#2166ac"}


def _path_d(points: Polygon) -> str:
    head, *rest = points
    return f"M {head[0]:.3f},{head[1]:.3f} L " + " ".join(f"{x:.3f},{y:.3f}" for x, y in rest) + " Z"


def _svg_open(layout: Layout, title: str) -> List[str]:
    s = layout.sheet
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="{s.width:g}mm" height="{s.height:g}mm" '
        f'viewBox="0 0 {s.width:g} {s.height:g}">',
        f"  <title>{escape(title)}</title>",
    ]


def cut_svg(layout: Layout) -> str:
    out = _svg_open(layout, f"Film cut lines - {layout.frame.name}")
    out.append(f'  <g id="cut" fill="none" stroke="{CUT_COLOR}" stroke-width="0.1">')
    for p in layout.placements:
        out.append(f'    <path id="cut-{p.side}" d="{_path_d(p.outline)}" />')
    out += ["  </g>", "</svg>", ""]
    return "\n".join(out)


def preview_svg(layout: Layout) -> str:
    s = layout.sheet
    out = _svg_open(layout, f"Film layout preview - {layout.frame.name}")
    out.append(f'  <rect x="0" y="0" width="{s.width:g}" height="{s.height:g}" fill="#0b3466" />')
    cy = s.center_from_top
    out.append(
        f'  <line x1="0" y1="{cy:g}" x2="{s.width:g}" y2="{cy:g}" stroke="#9ecae1" stroke-width="0.2" />'
    )
    for p in layout.placements:
        fx, fy = p.film_center
        r = s.film_diameter / 2
        color = EYE_COLOR[p.side]
        out += [
            f'  <g id="film-{p.slot}">',
            f'    <circle cx="{fx:.3f}" cy="{fy:.3f}" r="{r:g}" fill="none" stroke="white" stroke-width="0.8" />',
            f'    <line x1="{fx:.3f}" y1="{fy - r:.3f}" x2="{fx:.3f}" y2="{fy + r:.3f}" stroke="#9ecae1" stroke-width="0.2" />',
            f'    <circle cx="{fx:.3f}" cy="{fy:.3f}" r="{s.clear_zone_diameter / 2:g}" fill="white" stroke="#9ecae1" stroke-width="0.2" />',
            f'    <path d="{_path_d(p.outline)}" fill="{color}" fill-opacity="0.35" '
            f'stroke="{CUT_COLOR if p.fits else "#ffbf00"}" stroke-width="0.4" />',
            f'    <text x="{fx:.3f}" y="{fy + r + 5:.3f}" font-family="sans-serif" font-size="3.5" '
            f'fill="white" text-anchor="middle">{SIDE_NAME[p.side]} lens - PD {layout.measurements.pd(p.side):g} / '
            f'H {layout.measurements.height(p.side):g}</text>',
            "  </g>",
        ]
        # pupil mark: always at the film centre
        out.append(
            f'  <path d="M {fx - 1.5:.3f},{fy - 1.5:.3f} L {fx + 1.5:.3f},{fy + 1.5:.3f} M {fx - 1.5:.3f},{fy + 1.5:.3f} '
            f'L {fx + 1.5:.3f},{fy - 1.5:.3f}" stroke="black" stroke-width="0.4" />'
        )
    out += ["</svg>", ""]
    return "\n".join(out)


def plt(layout: Layout, units_per_mm: float = 40.0) -> str:
    """HPGL: origin at the sheet's bottom-left corner, y up."""
    h = layout.sheet.height
    cmds = ["IN", "SP1"]
    for p in layout.placements:
        pts = [(round(x * units_per_mm), round((h - y) * units_per_mm)) for x, y in p.outline]
        pts.append(pts[0])
        cmds.append(f"PU{pts[0][0]},{pts[0][1]}")
        cmds.append("PD" + ",".join(f"{x},{y}" for x, y in pts[1:]))
    cmds += ["PU", "SP0"]
    return ";\n".join(cmds) + ";\n"


def dxf(layout: Layout) -> str:
    """AutoCAD R12 DXF, millimetres, origin at the sheet's bottom-left corner, y up."""
    h = layout.sheet.height
    out = [
        "0", "SECTION", "2", "HEADER",
        "9", "$ACADVER", "1", "AC1009",
        "9", "$INSUNITS", "70", "4",
        "9", "$MEASUREMENT", "70", "1",
        "9", "$EXTMIN", "10", "0.0", "20", "0.0",
        "9", "$EXTMAX", "10", f"{layout.sheet.width:.3f}", "20", f"{h:.3f}",
        "0", "ENDSEC",
        "0", "SECTION", "2", "ENTITIES",
    ]
    for p in layout.placements:
        out += ["0", "POLYLINE", "8", f"CUT_{p.side}", "66", "1", "70", "1"]
        for x, y in p.outline:
            out += ["0", "VERTEX", "8", f"CUT_{p.side}", "10", f"{x:.4f}", "20", f"{h - y:.4f}"]
        out += ["0", "SEQEND", "8", f"CUT_{p.side}"]
    out += ["0", "ENDSEC", "0", "EOF"]
    return "\n".join(out) + "\n"


FORMATS = {
    "cut.svg": cut_svg,
    "preview.svg": preview_svg,
    "dxf": dxf,
    "plt": plt,
}
