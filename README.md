# filmcut: MyoPREVA film cutting frame designer

Makes cutter files (SVG, DXF, PLT) that cut a spectacle frame's lens shapes
out of a pre-printed MyoPREVA film sheet, positioned so that **each film
centre lands on the wearer's pupil** rather than on the lens's geometric
centre.

```
frame shape  ─┐
(library,     │   centre on lens box   ┌─ shift by PD / height ─┐
 .OMA scan,   ├─► (boxing system)  ───►│ pupil on film centre   ├─► cut.svg / .dxf / .plt
 .svg, .plt) ─┘                        └────────────────────────┘
```

## How the position is worked out

All in mm, using the optical boxing system (A = lens width, B = lens height,
DBL = bridge):

| quantity | formula |
|---|---|
| frame PD | A + DBL (e.g. eye 52 + bridge 18 = 70) |
| horizontal inset (per eye) | frame PD / 2 − monocular PD; positive = pupil is nasal of the lens centre |
| vertical offset (per eye) | fitting height − frame height; frame height defaults to B / 2 (the lens box centre, measured up from the lowest point of the lens) |

The lens outline is then drawn with its box centre at
*film centre − pupil offset*, so the pupil sits exactly on the film centre.

Worked example from the slides: frame PD 70, left PD 29, right PD 31,
frame height 30, fitting height 28 →
left pupil 6 mm nasal, right pupil 4 mm nasal, both 2 mm below the lens
centre. That is `tests/test_filmcut.py::test_slide_example_decentration`.

Both the frame PD and the frame height can be overridden (`--frame-pd`,
`--frame-height`) if a frame's reference points differ from the boxing centre.

### Film sheet

Defaults are measured from the slides and live in `filmcut.fitting.FilmSheet`:

| | mm |
|---|---|
| sheet | 193.1 × 110 |
| left film centre from the left edge | 56.8 |
| film centre to centre | 79.5 |
| film centre line from the top edge | 58 (52 to the bottom) |
| film circle diameter | 72 (estimated from the artwork; `--film-diameter`) |

A warning is printed (and the outline is drawn amber in the preview) when a
cut line would reach beyond the film circle.

### Which lens goes where

`--view wearer` (default) lays the sheet out as in the slides: the **left lens
on the left film**, as seen from behind the glasses. `--view front` mirrors
it (right lens on the left), which is how tracers and `omaconvert` draw frames.
Either way the nasal side of each lens faces the middle of the sheet.

## Frame shape sources

- **Catalogue** (`filmcut/data/frames.json`): named frame models built from
  a built-in shape plus eye / bridge / (optional) lens height, or pointing at
  a traced file. `filmcut frames [search words]` lists them.
- **Built-in shapes**: `wayfarer`, `square`, `panto`, `p3` (traced from the
  example outlines in the slides), plus `oval`, `round`, `rectangle`. Scaled
  to exactly A × B.
- **Scanner `.OMA` files**, decoded with
  [`omaconvert`](https://github.com/yangadeline-ai/Converting-OMA-files)
  (HBOX/VBOX/DBL come from the file).
- **`.svg` / `.plt`**, either as written by `omaconvert` (both lenses side by
  side; the bridge is measured from the gap) or a single lens outline (the
  other lens is mirrored from it; pass `--bridge`). SVG paths, curves, arcs,
  transforms and mm/cm/in/px units are handled.

## Outputs

| file | for |
|---|---|
| `NAME.cut.svg` | cut lines only, sheet-sized page in mm (Silhouette Studio Designer Edition and up, Cricut Design Space, Inkscape) |
| `NAME.dxf` | R12 polylines in mm (Silhouette Studio **Basic** Edition opens DXF, not SVG) |
| `NAME.plt` | HPGL, 40 units/mm, origin bottom-left (Graphtec, Roland and other plotter cutters) |
| `NAME.preview.svg` | the sheet with film circles, pupil marks and outlines, for checking; do not cut this one |

Every output uses the whole film sheet as its page, so a sheet aligned to the
cutter's origin (or to the page in Silhouette Studio) is cut in place.

## Use

```bash
pip install -e '.[test]'      # pulls omaconvert from GitHub

# a catalogue frame
filmcut design --frame generic-wayfarer-52-18 --pd 31 29 --height 28 28 -o out/

# a built-in shape at a given size
filmcut design --shape panto --eye 50 --bridge 20 --pd 32 32 --height 20 20 -o out/

# a scanner file
filmcut design --file job123.OMA --pd 32 31.5 --height 22 22 -o out/

# the web form (frame search, PD and fitting height per eye, preview, downloads)
filmcut serve            # then open http://127.0.0.1:8000/
```

`--pd` and `--height` take the RIGHT value first, then LEFT.
Other options: `--cut-offset -0.5` shrinks the cut line by 0.5 mm,
`--lens-height` sets B for a built-in shape, `--file-side L` says a single
traced outline is the left lens, `-f cut.svg -f dxf` limits the outputs.
`filmcut design --help` lists everything.

As a library:

```python
from filmcut import Catalogue, Measurements, build_layout, cut_svg

frame = Catalogue.load().get("generic-wayfarer-52-18").frame()
layout = build_layout(frame, Measurements(pd_right=31, pd_left=29, height_right=28, height_left=28))
print(layout.report())
open("job.cut.svg", "w").write(cut_svg(layout))
```

## Tests

```bash
python3 -m pytest tests -q
```

## Layout

```
filmcut/
  geometry.py   polygon helpers (bounding box, mirror, offset, smoothing)
  shapes.py     built-in lens shapes and the FrameShape model
  sources.py    .OMA (via omaconvert), .svg and .plt loaders
  library.py    frame catalogue (data/frames.json)
  fitting.py    film sheet, PD / height decentration, layout
  writers.py    cut.svg, preview.svg, DXF, PLT
  cli.py        `filmcut` command
  web.py        `filmcut serve` web form (static/index.html)
tests/
```
