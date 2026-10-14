"""Check the desktop pet's frame coverage and walking continuity."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
CELL_W, CELL_H = 256, 277


def cells(path: Path, columns: int, rows: int) -> list[np.ndarray]:
    with Image.open(path) as source:
        image = source.convert("RGBA")
    expected = (columns * CELL_W, rows * CELL_H)
    if image.size != expected:
        raise ValueError(f"{path.name}: {image.size}, expected {expected}")
    return [np.asarray(image.crop((column * CELL_W, row * CELL_H,
                                  (column + 1) * CELL_W,
                                  (row + 1) * CELL_H)))
            for row in range(rows) for column in range(columns)]


def main() -> None:
    walk = cells(ROOT / "assets" / "walk-right.png", 8, 8)
    idle = cells(ROOT / "assets" / "idle.png", 6, 1)
    walk_visible = [int((frame[:, :, 3] > 0).sum()) for frame in walk]
    idle_visible = [int((frame[:, :, 3] > 0).sum()) for frame in idle]
    distinct = len({hashlib.sha256(frame.tobytes()).digest() for frame in walk})
    differences = [float(np.abs(walk[i].astype(np.int16)
                                - walk[(i + 1) % 64].astype(np.int16)).mean())
                   for i in range(64)]
    magenta_edges = 0
    for frame in walk:
        r, g, b = (frame[:, :, channel].astype(np.int16)
                   for channel in range(3))
        hidden = Image.fromarray(np.where(frame[:, :, 3] == 0, 255, 0)
                                     .astype("uint8"))
        edge = np.asarray(hidden.filter(ImageFilter.MaxFilter(7))) > 0
        magenta_edges += int(((frame[:, :, 3] > 0) & edge &
                              (r > g + 35) & (b > g + 30) &
                              (g < 80) & (r > 70) & (b > 70)).sum())
    report = {
        "walk_frames": len(walk),
        "idle_frames": len(idle),
        "distinct_walk_frames": distinct,
        "min_visible_pixels_walk": min(walk_visible),
        "min_visible_pixels_idle": min(idle_visible),
        "mean_adjacent_change": round(float(np.mean(differences)), 3),
        "largest_adjacent_change": round(max(differences), 3),
        "loop_seam_change": round(differences[-1], 3),
        "strong_magenta_edge_pixels": magenta_edges,
    }
    report["ok"] = (len(walk) == 64 and len(idle) == 6 and
                    distinct == 64 and min(walk_visible) > 1000 and
                    min(idle_visible) > 1000 and magenta_edges <= 64 and
                    differences[-1] <= max(differences[:-1]) * 1.5)
    (ROOT / "asset-check.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
