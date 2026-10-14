"""Extract or rebuild the editable 8 x 11 Codex pet atlas."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "pet" / "m3" / "spritesheet.webp"
FRAMES = ROOT / "frames"
COLUMNS, ROWS = 8, 11
WIDTH, HEIGHT = 192, 208


def frame_path(row: int, column: int) -> Path:
    return FRAMES / f"row-{row:02d}" / f"frame-{column:02d}.png"


def extract() -> None:
    with Image.open(ATLAS) as source:
        atlas = source.convert("RGBA")
    if atlas.size != (COLUMNS * WIDTH, ROWS * HEIGHT):
        raise ValueError(f"Unexpected atlas size: {atlas.size}")
    for row in range(ROWS):
        for column in range(COLUMNS):
            path = frame_path(row, column)
            path.parent.mkdir(parents=True, exist_ok=True)
            box = (column * WIDTH, row * HEIGHT,
                   (column + 1) * WIDTH, (row + 1) * HEIGHT)
            atlas.crop(box).save(path)
    print(f"Extracted {COLUMNS * ROWS} cells to {FRAMES}")


def build() -> None:
    atlas = Image.new("RGBA", (COLUMNS * WIDTH, ROWS * HEIGHT))
    for row in range(ROWS):
        for column in range(COLUMNS):
            path = frame_path(row, column)
            with Image.open(path) as source:
                frame = source.convert("RGBA")
            if frame.size != (WIDTH, HEIGHT):
                raise ValueError(f"Unexpected size for {path}: {frame.size}")
            atlas.alpha_composite(frame, (column * WIDTH, row * HEIGHT))
    atlas.save(ATLAS, format="WEBP", lossless=True, quality=100,
               method=6, exact=True)
    print(f"Saved {ATLAS}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("extract", "build"))
    args = parser.parse_args()
    {"extract": extract, "build": build}[args.action]()
