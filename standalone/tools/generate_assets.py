"""Build high-density desktop animation sheets from the pet artwork.

The walking cycle interpolates the two-foot rig in scripts/rig_walk.py to
64 poses. The original 8 key poses remain anchors, so the near and far feet
keep their support order as the stride advances.
"""

from __future__ import annotations

import math
import runpy
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "standalone" / "assets"
CELL_W, CELL_H = 256, 277
POSE_COUNT = 64
COLS = 8


def catmull(values: list[float], position: float) -> float:
    base = math.floor(position)
    t = position - base
    n = len(values)
    p0, p1, p2, p3 = (values[(base + offset) % n]
                       for offset in (-1, 0, 1, 2))
    return 0.5 * ((2 * p1) + (-p0 + p2) * t
                  + (2*p0 - 5*p1 + 4*p2 - p3) * t*t
                  + (-p0 + 3*p1 - 3*p2 + p3) * t*t*t)


def flatten(pose: tuple) -> tuple[float, ...]:
    nx, ny, fx, fy, nk, fk, na, fa = pose
    return nx, ny, fx, fy, nk[0], nk[1], fk[0], fk[1], na, fa


def pose_at(poses: list[tuple], phase: float) -> tuple[float, ...]:
    keyframes = list(map(flatten, poses))
    return tuple(catmull([keyframe[i] for keyframe in keyframes], phase)
                 for i in range(len(keyframes[0])))


def fit_source(frame: Image.Image) -> Image.Image:
    # This transform matches the character size and foot baseline in the
    # Codex atlas, while sampling the large source artwork directly.
    size = (round(272 * 0.36 * CELL_W / 192),
            round(724 * 0.354 * CELL_H / 208))
    scaled = frame.resize(size, Image.Resampling.LANCZOS)
    output = Image.new("RGBA", (CELL_W, CELL_H))
    output.paste(scaled, (round(46 * CELL_W / 192),
                          round(-24 * CELL_H / 208)))
    pixels = np.asarray(output).copy()
    r, g, b = (pixels[:, :, channel].astype(np.int16)
               for channel in range(3))
    hidden = Image.fromarray(np.where(pixels[:, :, 3] == 0, 255, 0)
                                 .astype("uint8"))
    edge = np.asarray(hidden.filter(ImageFilter.MaxFilter(7))) > 0
    purple = ((pixels[:, :, 3] > 0) & edge &
              (r > g + 35) & (b > g + 30) &
              (g < 80) & (r > 70) & (b > 70))
    clean = (pixels[:, :, 3] > 0) & ~purple
    for y, x in np.argwhere(purple):
        for radius in range(1, 7):
            y0, y1 = max(0, y-radius), min(CELL_H, y+radius+1)
            x0, x1 = max(0, x-radius), min(CELL_W, x+radius+1)
            candidates = np.argwhere(clean[y0:y1, x0:x1])
            if candidates.size:
                candidates[:, 0] += y0
                candidates[:, 1] += x0
                distance = (candidates[:, 0] - y)**2 + (candidates[:, 1] - x)**2
                yy, xx = candidates[np.argmin(distance)]
                pixels[y, x, :3] = pixels[yy, xx, :3]
                clean[y, x] = True
                break
    pixels[pixels[:, :, 3] == 0, :3] = 0
    return Image.fromarray(pixels, "RGBA")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rig = runpy.run_path(str(ROOT / "scripts" / "rig_walk.py"))
    poses = rig["poses"]
    scale = rig["SCALE"]
    source_w, source_h = rig["SW"], rig["SH"]
    body = rig["body"].resize((source_w * scale, source_h * scale),
                               Image.Resampling.LANCZOS)
    sheet = Image.new("RGBA", (COLS * CELL_W,
                                 (POSE_COUNT // COLS) * CELL_H))

    for index in range(POSE_COUNT):
        phase = index * len(poses) / POSE_COUNT
        nx, ny, fx, fy, nkx, nky, fkx, fky, na, fa = pose_at(poses, phase)
        bob = catmull(rig["body_bob"], phase)
        canvas = Image.new("RGBA", (source_w * scale, source_h * scale))
        rig["draw_leg"](canvas, (151, 481), (fkx, fky),
                        (fx - 20, fy - 65), False)
        rig["paste_boot"](canvas, fx, fy, fa)
        rig["draw_leg"](canvas, (150, 483), (nkx, nky),
                        (nx - 20, ny - 65), True)
        rig["paste_boot"](canvas, nx, ny, na)
        canvas.alpha_composite(body, (0, round(bob * scale)))
        frame = fit_source(canvas.resize((source_w, source_h),
                                         Image.Resampling.LANCZOS))
        sheet.alpha_composite(frame,
                              ((index % COLS) * CELL_W,
                               (index // COLS) * CELL_H))

    sheet.save(OUT / "walk-right.png", optimize=True)

    with Image.open(ROOT / "pet" / "m3" / "spritesheet.webp") as source:
        atlas = source.convert("RGBA")
    idle = Image.new("RGBA", (6 * CELL_W, CELL_H))
    for index in range(6):
        box = (index * 192, 0, (index + 1) * 192, 208)
        cell = atlas.crop(box).resize((CELL_W, CELL_H),
                                      Image.Resampling.LANCZOS)
        idle.alpha_composite(cell, (index * CELL_W, 0))
    idle.save(OUT / "idle.png", optimize=True)

    # A compact contact sheet makes leg continuity easy to inspect.
    samples = Image.new("RGBA", (8 * CELL_W, 2 * CELL_H), "#e8eee9")
    for i, index in enumerate(range(0, POSE_COUNT, 4)):
        src = ((index % COLS) * CELL_W, (index // COLS) * CELL_H)
        crop = sheet.crop((*src, src[0] + CELL_W, src[1] + CELL_H))
        samples.alpha_composite(crop, ((i % 8) * CELL_W,
                                       (i // 8) * CELL_H))
    samples.save(ROOT / "standalone" / "walk-contact-sheet.png")
    print(f"Generated {POSE_COUNT} walking poses and 6 idle frames in {OUT}")


if __name__ == "__main__":
    main()
