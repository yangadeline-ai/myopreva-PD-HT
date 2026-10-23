"""``filmcut`` command line."""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from .fitting import FilmSheet, Measurements, build_layout
from .library import DEFAULT_CATALOGUE, Catalogue
from .shapes import SHAPE_NAMES, library_frame
from .sources import load_shape_file
from .writers import FORMATS


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="filmcut",
        description="Lay out frame lens shapes on a MyoPREVA film sheet so each pupil sits on a film centre, "
        "and write cutter files (SVG / DXF / PLT).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    lst = sub.add_parser("frames", help="list or search the frame catalogue")
    lst.add_argument("query", nargs="?", default="")
    lst.add_argument("--catalogue", default=DEFAULT_CATALOGUE)

    d = sub.add_parser("design", help="make cutter files for one job")
    src = d.add_mutually_exclusive_group(required=True)
    src.add_argument("--frame", help="frame id from the catalogue (see `filmcut frames`)")
    src.add_argument("--shape", choices=SHAPE_NAMES, help="built-in lens shape (needs --eye and --bridge)")
    src.add_argument("--file", help="traced shape: .oma (scanner), .svg or .plt")
    d.add_argument("--catalogue", default=DEFAULT_CATALOGUE)
    d.add_argument("--eye", type=float, help="eye size A, mm")
    d.add_argument("--bridge", type=float, help="bridge / DBL, mm")
    d.add_argument("--lens-height", type=float, help="lens height B, mm (built-in shapes)")
    d.add_argument("--file-side", choices=["R", "L"], default="R", help="which lens a single-outline SVG/PLT is")
    d.add_argument("--file-view", choices=["front", "wearer"], default="front", help="view the SVG/PLT was drawn in")
    d.add_argument("--units-per-mm", type=float, default=40.0, help="HPGL units per mm (PLT in and out)")

    d.add_argument("--pd", type=float, nargs=2, metavar=("RIGHT", "LEFT"), required=True, help="monocular PD, mm")
    d.add_argument("--height", type=float, nargs=2, metavar=("RIGHT", "LEFT"), required=True, help="fitting height, mm")
    d.add_argument("--frame-pd", type=float, help="override frame PD (default A + DBL)")
    d.add_argument("--frame-height", type=float, help="override frame reference height (default B / 2)")
    d.add_argument("--view", choices=["wearer", "front"], default="wearer",
                   help="wearer: left lens on the left film (as in the slides); front: right lens on the left")
    d.add_argument("--cut-offset", type=float, default=0.0, help="grow (+) / shrink (-) the cut line, mm")
    d.add_argument("--film-diameter", type=float, default=FilmSheet.film_diameter)
    d.add_argument("--film-distance", type=float, default=FilmSheet.center_distance, help="film centre to centre, mm")
    d.add_argument("-f", "--format", action="append", choices=sorted(FORMATS) + ["all"],
                   help="output(s) to write (repeatable; default all)")
    d.add_argument("-o", "--outdir", default=".")
    d.add_argument("--name", help="output file name stem")

    w = sub.add_parser("serve", help="run the web form")
    w.add_argument("--host", default="127.0.0.1")
    w.add_argument("--port", type=int, default=8000)
    w.add_argument("--catalogue", default=DEFAULT_CATALOGUE)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "frames":
        for m in Catalogue.load(args.catalogue).search(args.query):
            print(f"{m.id:28s} {m.label:30s} shape={m.shape or m.file}")
        return 0

    if args.command == "serve":
        from .web import serve

        serve(args.host, args.port, args.catalogue)
        return 0

    if args.frame:
        frame = Catalogue.load(args.catalogue).get(args.frame).frame(args.eye, args.bridge, args.lens_height)
        stem = args.name or args.frame
    elif args.shape:
        if args.eye is None or args.bridge is None:
            print("--shape needs --eye and --bridge", file=sys.stderr)
            return 2
        frame = library_frame(args.shape, args.eye, args.bridge, args.lens_height)
        stem = args.name or f"{args.shape}-{args.eye:g}-{args.bridge:g}"
    else:
        frame = load_shape_file(args.file, side=args.file_side, bridge=args.bridge,
                                input_view=args.file_view, units_per_mm=args.units_per_mm)
        stem = args.name or os.path.splitext(os.path.basename(args.file))[0]

    sheet = FilmSheet(film_diameter=args.film_diameter, center_distance=args.film_distance)
    sheet.width = 2 * sheet.left_center_x + sheet.center_distance
    layout = build_layout(
        frame,
        Measurements(args.pd[0], args.pd[1], args.height[0], args.height[1]),
        sheet,
        view=args.view,
        frame_pd=args.frame_pd,
        frame_height=args.frame_height,
        cut_offset=args.cut_offset,
    )
    print(layout.report())

    formats = sorted(FORMATS) if not args.format or "all" in args.format else args.format
    os.makedirs(args.outdir, exist_ok=True)
    for fmt in formats:
        path = os.path.join(args.outdir, f"{stem}.{fmt}")
        writer = FORMATS[fmt]
        text = writer(layout, args.units_per_mm) if fmt == "plt" else writer(layout)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
