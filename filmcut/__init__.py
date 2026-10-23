"""filmcut: lay out spectacle-frame lens shapes on MyoPREVA film sheets for cutting machines."""

from .fitting import FilmSheet, Layout, Measurements, build_layout
from .library import Catalogue, FrameModel
from .shapes import SHAPE_NAMES, FrameShape, library_frame
from .sources import load_shape_file, load_shape_text
from .writers import FORMATS, cut_svg, dxf, plt, preview_svg

__version__ = "0.1.0"

__all__ = [
    "Catalogue",
    "FilmSheet",
    "FORMATS",
    "FrameModel",
    "FrameShape",
    "Layout",
    "Measurements",
    "SHAPE_NAMES",
    "build_layout",
    "cut_svg",
    "dxf",
    "library_frame",
    "load_shape_file",
    "load_shape_text",
    "plt",
    "preview_svg",
]
