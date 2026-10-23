"""Minimal web form (standard library only): pick a frame, enter PD and heights, download cutter files."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

from .fitting import FilmSheet, Measurements, build_layout
from .library import DEFAULT_CATALOGUE, Catalogue
from .shapes import SHAPE_NAMES, library_frame
from .sources import load_shape_text
from .writers import FORMATS

STATIC = os.path.join(os.path.dirname(__file__), "static")
MAX_BODY = 5 * 1024 * 1024


def _num(v: Any) -> Any:
    return None if v in (None, "") else float(v)


def design(req: Dict[str, Any], catalogue: Catalogue) -> Dict[str, Any]:
    """Turn one JSON request from the form into a layout and all output files."""
    eye, bridge, lens_h = _num(req.get("eye")), _num(req.get("bridge")), _num(req.get("lens_height"))
    upload = req.get("file")
    if upload:
        ext = os.path.splitext(upload.get("name", ""))[1]
        frame = load_shape_text(
            upload["text"], ext, side=req.get("file_side", "R"), bridge=bridge,
            input_view=req.get("file_view", "front"), name=upload.get("name", ""),
        )
    elif req.get("frame_id"):
        frame = catalogue.get(req["frame_id"]).frame(eye, bridge, lens_h)
    elif req.get("shape"):
        if eye is None or bridge is None:
            raise ValueError("Enter the eye size and bridge for a built-in shape")
        frame = library_frame(req["shape"], eye, bridge, lens_h)
    else:
        raise ValueError("Choose a frame model, a built-in shape or upload a traced shape file")

    m = Measurements(float(req["pd_right"]), float(req["pd_left"]), float(req["height_right"]), float(req["height_left"]))
    layout = build_layout(
        frame, m, FilmSheet(), view=req.get("view", "wearer"),
        frame_pd=_num(req.get("frame_pd")), frame_height=_num(req.get("frame_height")),
        cut_offset=_num(req.get("cut_offset")) or 0.0,
    )
    return {
        "report": layout.report(),
        "warnings": layout.warnings + frame.notes,
        "frame": {"name": frame.name, "a": round(frame.a("R"), 2), "b": round(frame.b("R"), 2),
                  "dbl": round(frame.dbl, 2), "frame_pd": round(layout.frame_pd, 2)},
        "files": {fmt: writer(layout) for fmt, writer in FORMATS.items()},
    }


def make_handler(catalogue: Catalogue):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, data: Any) -> None:
            self._send(code, json.dumps(data).encode(), "application/json")

        def do_GET(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                with open(os.path.join(STATIC, "index.html"), "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            elif url.path == "/api/frames":
                q = parse_qs(url.query).get("q", [""])[0]
                self._json(200, {
                    "shapes": SHAPE_NAMES,
                    "frames": [
                        {"id": m.id, "label": m.label, "eye": m.eye, "bridge": m.bridge, "temple": m.temple,
                         "height": m.height, "shape": m.shape}
                        for m in catalogue.search(q)
                    ],
                })
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/api/design":
                self._send(404, b"not found", "text/plain")
                return
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_BODY:
                self._json(413, {"error": "Upload too large"})
                return
            try:
                self._json(200, design(json.loads(self.rfile.read(length)), catalogue))
            except (KeyError, ValueError, TypeError) as exc:
                self._json(400, {"error": str(exc)})

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8000, catalogue_path: str = DEFAULT_CATALOGUE) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(Catalogue.load(catalogue_path)))
    print(f"filmcut web form on http://{host}:{port}/  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
