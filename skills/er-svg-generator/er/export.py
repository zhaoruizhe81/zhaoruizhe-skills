from __future__ import annotations

import json
from pathlib import Path

from .model import Layout


POSITION_PRECISION = 4


def export_layout(layout: Layout, path: Path) -> None:
    data = {"layout": {"positions": {"entities": {}, "relationships": {}}}}
    for node in layout.nodes.values():
        if node.kind == "entity":
            data["layout"]["positions"]["entities"][node.id] = {
                "x": round(node.x, POSITION_PRECISION),
                "y": round(node.y, POSITION_PRECISION),
            }
        elif node.kind == "relationship" and node.id.startswith("rel:"):
            data["layout"]["positions"]["relationships"][node.id.removeprefix("rel:")] = {
                "x": round(node.x, POSITION_PRECISION),
                "y": round(node.y, POSITION_PRECISION),
            }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
