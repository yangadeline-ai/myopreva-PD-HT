import math
import os
import subprocess
import sys

import pytest

from filmcut import (
    Catalogue,
    FilmSheet,
    Measurements,
    build_layout,
    cut_svg,
    dxf,
    library_frame,
    load_shape_file,
    load_shape_text,
    plt,
    preview_svg,
)
from filmcut.geometry import bounds, box_center, box_size, max_radius, offset, signed_area
from filmcut.shapes import SHAPE_NAMES, library_outline
from filmcut.sources import parse_hpgl, parse_path_d, parse_svg
from filmcut.web import design

HERE = os.path.dirname(__file__)
OMA = os.path.join(HERE, "..", "filmcut", "data", "traces", "146987.OMA")


def slide_layout(**kw):
    """The worked example in the MyoPREVA slides."""
    frame = library_frame("wayfarer", 52, 18)
    return build_layout(frame, Measurements(31, 29, 28, 28), frame_height=30, **kw)


# ---------------------------------------------------------------- shapes


@pytest.mark.parametrize("name", SHAPE_NAMES)
def test_library_outline_is_boxed_exactly(name):
    pts = library_outline(name, 52, 40)
    w, h = box_size(pts)
    assert w == pytest.approx(52, abs=0.05)
    assert h == pytest.approx(40, abs=0.05)
    assert box_center(pts) == pytest.approx((0, 0), abs=0.05)
    assert signed_area(pts) > 0


def test_library_frame_left_is_mirror_of_right():
    f = library_frame("wayfarer", 52, 18)
    r = sorted((round(x, 3), round(y, 3)) for x, y in f.outlines["R"])
    l = sorted((round(-x, 3), round(y, 3)) for x, y in f.outlines["L"])
    assert r == l
    assert f.frame_pd == pytest.approx(70)


def test_wayfarer_nasal_side_is_plus_x_for_right_lens():
    # the slanted lower corner (nasal) is where the bottom edge rises: compare
    # how low the outline goes near each side
    pts = library_outline("wayfarer", 52, 40)
    low_nasal = min(y for x, y in pts if x > 20)
    low_temporal = min(y for x, y in pts if x < -20)
    assert low_nasal > low_temporal


# ---------------------------------------------------------------- fitting


def test_slide_example_decentration():
    lay = slide_layout()
    by_side = {p.side: p for p in lay.placements}
    assert lay.frame_pd == pytest.approx(70)
    assert by_side["L"].inset == pytest.approx(6)  # "move right 6mm"
    assert by_side["R"].inset == pytest.approx(4)  # "move left 4mm"
    assert by_side["L"].vertical == pytest.approx(-2)  # "move down 2mm"
    assert by_side["R"].vertical == pytest.approx(-2)
    # wearer view: left lens on the left film circle, as in the slides
    assert by_side["L"].slot == "left" and by_side["R"].slot == "right"


def test_pupil_lands_on_film_centre():
    """The box centre on the sheet must be offset from the film centre by exactly the pupil offset."""
    lay = slide_layout()
    for p in lay.placements:
        cx, cy = box_center(p.outline)
        fx, fy = p.film_center
        nasal_dir = 1 if p.slot == "left" else -1  # wearer view: nose is towards the sheet middle
        # pupil = box centre + inset towards the nose, + vertical up (sheet y is down)
        assert cx + nasal_dir * p.inset == pytest.approx(fx, abs=0.05)
        assert cy - p.vertical == pytest.approx(fy, abs=0.05)


def test_front_view_swaps_slots_and_mirrors():
    w = slide_layout(view="wearer")
    f = slide_layout(view="front")
    assert {p.side: p.slot for p in f.placements} == {"R": "left", "L": "right"}
    sheet = FilmSheet()
    mid = sheet.width / 2
    # the front-view layout is the wearer-view layout reflected about the sheet's middle
    wl = sorted((round(2 * mid - x, 2), round(y, 2)) for p in w.placements for x, y in p.outline)
    fl = sorted((round(x, 2), round(y, 2)) for p in f.placements for x, y in p.outline)
    assert wl == fl


def test_default_frame_height_is_half_b():
    frame = library_frame("panto", 50, 20, 36)
    lay = build_layout(frame, Measurements(35, 35, 18, 20))
    by_side = {p.side: p for p in lay.placements}
    assert by_side["R"].vertical == pytest.approx(0, abs=0.05)
    assert by_side["L"].vertical == pytest.approx(2, abs=0.05)
    assert by_side["R"].inset == pytest.approx(0)


def test_warns_when_shape_leaves_film():
    frame = library_frame("rectangle", 62, 14, 45)
    lay = build_layout(frame, Measurements(28, 28, 10, 10))
    assert lay.warnings and not all(p.fits for p in lay.placements)


def test_cut_offset_moves_edge():
    plain = slide_layout()
    shrunk = slide_layout(cut_offset=-0.5)
    for a, b in zip(plain.placements, shrunk.placements):
        wa, ha = box_size(a.outline)
        wb, hb = box_size(b.outline)
        assert wb == pytest.approx(wa - 1.0, abs=0.05)
        assert hb == pytest.approx(ha - 1.0, abs=0.05)


def test_offset_of_circle_changes_radius():
    circle = [(10 * math.cos(t), 10 * math.sin(t)) for t in (2 * math.pi * i / 360 for i in range(360))]
    for d in (1.0, -2.0):
        assert max_radius(offset(circle, d)) == pytest.approx(10 + d, abs=0.01)


# ---------------------------------------------------------------- sources


def test_oma_loads_both_lenses_centred():
    f = load_shape_file(OMA)
    assert set(f.outlines) == {"R", "L"}
    assert f.dbl == pytest.approx(16.99)
    assert f.a("R") == pytest.approx(54.39, abs=0.3)
    assert f.b("R") == pytest.approx(42.62, abs=0.3)
    for side in "RL":
        assert box_center(f.outlines[side]) == pytest.approx((0, 0), abs=1e-6)


@pytest.fixture(scope="module")
def omaconvert_outputs(tmp_path_factory):
    out = tmp_path_factory.mktemp("oma")
    subprocess.run([sys.executable, "-m", "omaconvert.cli", OMA, "-f", "both", "-o", str(out)], check=True,
                   capture_output=True)
    return out


@pytest.mark.parametrize("ext", ["svg", "plt"])
def test_omaconvert_output_round_trips(omaconvert_outputs, ext):
    """SVG/PLT written by omaconvert give the same frame as reading the .OMA directly."""
    direct = load_shape_file(OMA)
    via = load_shape_file(str(omaconvert_outputs / f"146987.{ext}"))
    assert via.dbl == pytest.approx(direct.dbl, abs=0.1)
    for side in "RL":
        assert via.a(side) == pytest.approx(direct.a(side), abs=0.1)
        assert via.b(side) == pytest.approx(direct.b(side), abs=0.1)
        # same orientation: the nasal half (+x for R) is the same size in both
        def nasal_area(pts, s):
            sign = 1 if s == "R" else -1
            return sum(1 for x, _ in pts if sign * x > 0)
        assert abs(nasal_area(via.outlines[side], side) - nasal_area(direct.outlines[side], side)) < 20


def test_single_outline_svg_is_mirrored_for_other_eye():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="60mm" height="50mm" viewBox="0 0 60 50">'
           '<path d="M 5 10 L 55 5 L 50 45 L 10 40 Z"/></svg>')
    f = load_shape_text(svg, "svg", side="R", bridge=18)
    assert f.dbl == 18
    assert box_size(f.outlines["R"]) == pytest.approx((50, 40), abs=0.01)
    # mirrored: R's top-right corner (nasal, high) matches L's top-left
    r_top = max(f.outlines["R"], key=lambda p: p[1])
    l_top = max(f.outlines["L"], key=lambda p: p[1])
    assert r_top[0] == pytest.approx(-l_top[0], abs=0.01)


def test_svg_units_and_transforms():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="10cm" height="5cm" viewBox="0 0 1000 500">'
           '<g transform="translate(100,50) scale(2)"><rect x="0" y="0" width="200" height="100"/></g></svg>')
    (poly,) = parse_svg(svg)
    x0, y0, x1, y1 = bounds(poly)
    assert (x1 - x0, y1 - y0) == pytest.approx((40, 20))
    assert x0 == pytest.approx(10)


def test_path_curves_and_arcs():
    (circle,) = parse_path_d("M 0 10 A 10 10 0 1 1 0 -10 A 10 10 0 1 1 0 10 Z")
    assert max_radius(circle) == pytest.approx(10, abs=1e-6)
    assert min(math.hypot(*p) for p in circle) == pytest.approx(10, abs=1e-6)
    (curve,) = parse_path_d("m 0 0 c 10 0 10 10 10 10 s -10 10 -10 10 q -5 -10 0 -20 z")
    assert curve[-1] == pytest.approx((0, 0))


# ---------------------------------------------------------------- writers


def test_plt_round_trips_to_layout():
    lay = slide_layout()
    polys = parse_hpgl(plt(lay))
    assert len(polys) == 2
    h = lay.sheet.height
    for poly, p in zip(polys, lay.placements):
        x0, y0, x1, y1 = bounds(poly)
        ex0, ey0, ex1, ey1 = bounds(p.outline)
        assert (x0, x1) == pytest.approx((ex0, ex1), abs=0.03)
        assert (y0, y1) == pytest.approx((h - ey1, h - ey0), abs=0.03)


def test_cut_svg_only_contains_cut_lines():
    lay = slide_layout()
    text = cut_svg(lay)
    assert 'width="193.1mm"' in text and 'height="110mm"' in text
    polys = parse_svg(text)
    assert len(polys) == 2
    # cut.svg re-imports as the same frame
    again = load_shape_text(text, "svg", input_view="wearer")
    assert again.a("R") == pytest.approx(lay.frame.a("R"), abs=0.05)
    assert "<circle" not in text and "<text" not in text
    assert "<circle" in preview_svg(lay)


def test_dxf_structure():
    text = dxf(slide_layout()).splitlines()
    assert text.count("POLYLINE") == 2 and text.count("SEQEND") == 2
    assert text[-1] == "EOF"


# ---------------------------------------------------------------- catalogue, web, cli


def test_catalogue_search_and_build():
    cat = Catalogue.load()
    hits = cat.search("wayfarer 52")
    assert [m.id for m in hits] == ["generic-wayfarer-52-18"]
    f = hits[0].frame()
    assert f.frame_pd == pytest.approx(70)
    assert f.b("R") == pytest.approx(40.9, abs=0.05)
    traced = cat.get("traced-146987").frame()
    assert traced.dbl == pytest.approx(16.99)


def test_web_design_with_upload_and_catalogue():
    cat = Catalogue.load()
    with open(OMA, encoding="latin-1") as fh:
        oma = fh.read()
    base = dict(pd_right="32", pd_left="31", height_right="22", height_left="22", view="wearer")
    res = design(dict(base, file={"name": "x.OMA", "text": oma}), cat)
    assert set(res["files"]) == {"cut.svg", "preview.svg", "dxf", "plt"}
    assert res["frame"]["dbl"] == pytest.approx(16.99)
    res = design(dict(base, frame_id="generic-square-52-18", bridge="20"), cat)
    assert res["frame"]["frame_pd"] == pytest.approx(72)
    with pytest.raises(ValueError):
        design(base, cat)


def test_cli_design(tmp_path):
    from filmcut.cli import main

    rc = main(["design", "--shape", "wayfarer", "--eye", "52", "--bridge", "18", "--pd", "31", "29",
               "--height", "28", "28", "--frame-height", "30", "-o", str(tmp_path), "--name", "job"])
    assert rc == 0
    assert sorted(os.listdir(tmp_path)) == ["job.cut.svg", "job.dxf", "job.plt", "job.preview.svg"]
