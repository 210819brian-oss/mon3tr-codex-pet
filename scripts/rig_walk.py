"""Art-directed two-foot walk for Mon3tr.

The upper sprite and boot art come from an imagegen row. Leg paths are drawn
as an explicit two-leg rig so support identity, contact and push stay stable.
"""
from __future__ import annotations

import math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "art-source" / "rig-source.png"
OUT = ROOT / "art-source" / "running-right-strip.png"
SCALE = 3
SW, SH = 272, 724
KEY = (255, 0, 255, 255)
INK = (22, 25, 29, 255)
SKIN = (255, 239, 222, 255)
SKIN_SHADE = (244, 207, 188, 255)
FAR_SKIN = (230, 217, 202, 255)
FAR_SHADE = (209, 189, 177, 255)


def keyed(im: Image.Image) -> Image.Image:
    a = np.array(im.convert("RGBA"))
    is_key = (a[:, :, 0] > 185) & (a[:, :, 2] > 185) & (a[:, :, 1] < 115)
    a[is_key] = 0
    red, green, blue = (a[:, :, c].astype(np.int16) for c in range(3))
    transparent = Image.fromarray(np.where(a[:, :, 3] == 0, 255, 0).astype("uint8"))
    edge = np.asarray(transparent.filter(ImageFilter.MaxFilter(9))) > 0
    magenta_like = ((red > green + 6) & (blue > green + 6)
                    & (red > 15) & (blue > 15))
    strong_magenta = ((red > green + 25) & (blue > green + 15)
                      & (red > 80) & (blue > 80))
    purple = ((a[:, :, 3] > 0) & (strong_magenta | (magenta_like & edge)))
    clean = (a[:, :, 3] > 0) & ~purple
    for y, x in np.argwhere(purple):
        for radius in range(1, 8):
            y0, y1 = max(0, y-radius), min(a.shape[0], y+radius+1)
            x0, x1 = max(0, x-radius), min(a.shape[1], x+radius+1)
            candidates = np.argwhere(clean[y0:y1, x0:x1])
            if candidates.size:
                candidates[:, 0] += y0
                candidates[:, 1] += x0
                dist2 = (candidates[:, 0] - y)**2 + (candidates[:, 1] - x)**2
                yy, xx = candidates[np.argmin(dist2)]
                a[y, x, :3] = a[yy, xx, :3]
                clean[y, x] = True
                break
    a[a[:, :, 3] == 0, :3] = 0
    return Image.fromarray(a)


def zero_hidden(im: Image.Image) -> Image.Image:
    a = np.array(im.convert("RGBA"))
    a[a[:, :, 3] == 0, :3] = 0
    return Image.fromarray(a)


src = Image.open(SOURCE).convert("RGBA")
assert src.size == (2172, 724), src.size
base = keyed(src.crop((0, 0, SW, SH)))

# Preserve hair, face, sleeves and dress, while clearing the source leg pose.
body_mask = Image.new("L", (SW, SH), 0)
md = ImageDraw.Draw(body_mask)
md.rectangle((0, 0, SW, 475), fill=255)
md.polygon([(68, 475), (91, 496), (172, 496), (188, 509),
            (229, 503), (239, 475)], fill=255)
body_mask = body_mask.filter(ImageFilter.GaussianBlur(0.35))
body = base.copy()
body.putalpha(Image.fromarray(np.minimum(np.asarray(body.getchannel("A")),
                                          np.asarray(body_mask)).astype("uint8")))
body = zero_hidden(body)

# Exact source boot silhouette and shading, used for both anatomical feet.
boot_mask = Image.new("L", (SW, SH), 0)
bm = ImageDraw.Draw(boot_mask)
bm.polygon([(157, 561), (178, 556), (217, 561), (249, 580),
            (262, 602), (262, 633), (221, 640), (172, 635), (159, 615)], fill=255)
boot = base.copy()
boot.putalpha(Image.fromarray(np.minimum(np.asarray(boot.getchannel("A")),
                                          np.asarray(boot_mask)).astype("uint8")))
boot_px = np.array(boot)
br, bg, bb = (boot_px[:, :, c].astype(np.int16) for c in range(3))
skin_fragment = (br > 160) & (br > bg + 12) & (bg > bb + 5)
boot_px[skin_fragment, 3] = 0
boot = zero_hidden(Image.fromarray(boot_px))
boot = boot.crop((155, 552, 264, 642))
boot = boot.resize((109 * SCALE, 90 * SCALE), Image.Resampling.LANCZOS)


def S(p):
    return tuple(round(v * SCALE) for v in p)


def draw_leg(canvas: Image.Image, hip, knee, foot, is_near: bool):
    draw = ImageDraw.Draw(canvas)
    pts = [S(hip), S(knee), S(foot)]
    fill = SKIN if is_near else FAR_SKIN
    shade = SKIN_SHADE if is_near else FAR_SHADE
    draw.line(pts, fill=INK, width=38 * SCALE, joint="curve")
    for x, y in pts:
        draw.ellipse((x - 19*SCALE, y - 19*SCALE,
                      x + 19*SCALE, y + 19*SCALE), fill=INK)
    draw.line(pts, fill=fill, width=31 * SCALE, joint="curve")
    for x, y in pts:
        draw.ellipse((x - 15*SCALE, y - 15*SCALE,
                      x + 15*SCALE, y + 15*SCALE), fill=fill)
    # Soft directional skin shade, below the skirt and above the boot cuff.
    draw.line([S((hip[0] + 8, hip[1] + 10)), S((knee[0] + 7, knee[1])),
               S((foot[0] + 4, foot[1] - 12))], fill=shade, width=4 * SCALE,
              joint="curve")
    if is_near:
        # The black thigh band is physically bound to the near leg throughout.
        t = 0.45
        cx = hip[0] + (knee[0] - hip[0]) * t
        cy = hip[1] + (knee[1] - hip[1]) * t
        dx = knee[0] - hip[0]
        dy = knee[1] - hip[1]
        n = math.hypot(dx, dy)
        px, py = -dy / n * 19, dx / n * 19
        a, b = S((cx - px, cy - py)), S((cx + px, cy + py))
        draw.line([a, b], fill=INK, width=13 * SCALE)
        draw.line([a, b], fill=(70, 74, 75, 255), width=7 * SCALE)
        bx, by = S((cx + px * 0.30, cy + py * 0.30))
        draw.rounded_rectangle((bx - 6*SCALE, by - 5*SCALE,
                                bx + 6*SCALE, by + 5*SCALE),
                               radius=2*SCALE, fill=INK)
        draw.rounded_rectangle((bx - 3*SCALE, by - 3*SCALE,
                                bx + 3*SCALE, by + 3*SCALE),
                               radius=SCALE, fill=(180, 184, 179, 255))


def paste_boot(canvas: Image.Image, cx: int, bottom: int, angle: float):
    piece = boot.rotate(angle, resample=Image.Resampling.BICUBIC,
                        expand=True)
    # Source boot art is centered around x~210; crop center is 209.5.
    left = round(cx * SCALE - piece.width / 2)
    top = round(bottom * SCALE - piece.height + 7*SCALE)
    canvas.alpha_composite(piece, (left, top))


# Foot x moves from front to back while it bears weight. Contact switches at
# the middle and again at the loop seam. Each tuple is (near x, near bottom,
# far x, far bottom, near knee x/y, far knee x/y, near angle, far angle).
poses = [
    (195, 637, 119, 618, (173, 539), (133, 535), 0, 0),
    (170, 637, 146, 590, (162, 543), (153, 521), 0, 0),
    (145, 637, 172, 610, (150, 546), (178, 530), 0, 0),
    (119, 637, 195, 637, (133, 541), (173, 539), 0, 0),
    (119, 618, 195, 637, (133, 535), (173, 539), 0, 0),
    (146, 590, 170, 637, (153, 521), (162, 543), 0, 0),
    (172, 610, 145, 637, (178, 530), (150, 546), 0, 0),
    (195, 637, 119, 637, (173, 539), (133, 541), 0, 0),
]
body_bob = [0, 1, 2, 1, 0, 1, 2, 1]

strip = Image.new("RGBA", (8 * SW, SH), (0, 0, 0, 0))
for i, (nx, ny, fx, fy, nk, fk, na, fa) in enumerate(poses):
    canvas = Image.new("RGBA", (SW*SCALE, SH*SCALE), (0, 0, 0, 0))
    draw_leg(canvas, (151, 481), fk, (fx - 20, fy - 65), False)
    paste_boot(canvas, fx, fy, fa)
    draw_leg(canvas, (150, 483), nk, (nx - 20, ny - 65), True)
    paste_boot(canvas, nx, ny, na)
    bg = body.resize((SW*SCALE, SH*SCALE), Image.Resampling.LANCZOS)
    canvas.alpha_composite(bg, (0, body_bob[i]*SCALE))
    frame = canvas.resize((SW, SH), Image.Resampling.LANCZOS)
    strip.alpha_composite(zero_hidden(frame), (i*SW, 0))

OUT.parent.mkdir(parents=True, exist_ok=True)
zero_hidden(strip).save(OUT)
print(OUT)
