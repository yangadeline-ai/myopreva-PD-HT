"""Frame catalogue: named frame models backed by a built-in shape or a traced file."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Optional

from .shapes import FrameShape, library_frame
from .sources import load_shape_file

DEFAULT_CATALOGUE = os.path.join(os.path.dirname(__file__), "data", "frames.json")


@dataclass
class FrameModel:
    id: str
    brand: str
    model: str
    eye: Optional[float] = None
    bridge: Optional[float] = None
    temple: Optional[float] = None
    height: Optional[float] = None
    shape: Optional[str] = None
    file: Optional[str] = None

    @property
    def label(self) -> str:
        size = f" {self.eye:g}-{self.bridge:g}" if self.eye and self.bridge else ""
        return f"{self.brand} {self.model}{size}"

    def matches(self, query: str) -> bool:
        hay = f"{self.id} {self.brand} {self.model} {self.shape or ''}".lower()
        return all(word in hay for word in query.lower().split())

    def frame(self, eye: Optional[float] = None, bridge: Optional[float] = None, height: Optional[float] = None) -> FrameShape:
        """Build the frame; ``eye``/``bridge``/``height`` override the catalogue size."""
        if self.file:
            frame = load_shape_file(self.file, bridge=bridge if bridge is not None else self.bridge)
            frame.name = self.label
            return frame
        eye = eye if eye is not None else self.eye
        bridge = bridge if bridge is not None else self.bridge
        if height is None and eye == self.eye:
            height = self.height
        if eye is None or bridge is None:
            raise ValueError(f"Frame {self.id} needs an eye size and bridge")
        return library_frame(self.shape or "oval", eye, bridge, height, name=self.label)


class Catalogue:
    def __init__(self, models: List[FrameModel]):
        self.models = models

    @classmethod
    def load(cls, path: str = DEFAULT_CATALOGUE) -> "Catalogue":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        base = os.path.dirname(os.path.abspath(path))
        models = []
        for entry in data.get("frames", []):
            entry = dict(entry)
            if entry.get("file"):
                entry["file"] = os.path.join(base, entry["file"])
            models.append(FrameModel(**entry))
        return cls(models)

    def search(self, query: str = "") -> List[FrameModel]:
        return [m for m in self.models if m.matches(query)] if query else list(self.models)

    def get(self, frame_id: str) -> FrameModel:
        for m in self.models:
            if m.id == frame_id:
                return m
        raise KeyError(f"No frame {frame_id!r} in the catalogue")
