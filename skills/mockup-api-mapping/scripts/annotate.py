#!/usr/bin/env python3
"""
Reusable annotator for the mockup-api-mapping skill.

Draws numbered circular markers with a short connector line pointing at a UI
element, colored green (confirmed against the spec) or red (gap - no matching
field). Import mark_points()/composite_side_by_side() directly from a one-off
script for a given report, or run this file for a tiny self-test.

Usage pattern (typical per-screenshot script):

    from annotate import mark_points
    from PIL import Image

    img = Image.open("input.png").convert("RGB")
    points = [
        # (x, y_top_of_text, number, confirmed_bool)
        (285, 614, 1, True),
        (285, 978, 2, False),
    ]
    mark_points(img, points)
    img.save("ANNOTATED-input.png")

Coordinate-finding workflow (see SKILL.md step 5 for the full loop):
  1. Read the raw screenshot with the Read tool and eyeball approximate
     (x, y) for each element's left edge / top edge.
  2. Write the points list, run the script, Read the annotated output back.
  3. If a marker overlaps text, sits on the wrong UI element (e.g. a nav
     sidebar instead of the content pane), or two markers collide, adjust
     coordinates and re-render. Budget at least one correction pass - first-try
     coordinates are frequently off by one "column" (nav vs. content) or one
     row.
"""

from PIL import Image, ImageDraw, ImageFont

GREEN = (26, 127, 55)
RED = (207, 34, 46)
GREEN_BG = (218, 251, 225)
RED_BG = (255, 235, 233)


def _font(size=13, bold=True):
    paths = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def mark_points(img, points, font_size=13, radius=11, connector_len=16):
    """Draw numbered circle+connector markers directly onto `img` (in place).

    points: list of (x, y_top, number, confirmed) tuples.
      - x, y_top: the top-left-ish anchor of the UI text/element being called out.
        The circle is drawn ABOVE this point; a short vertical line connects
        circle to element. Pick x near the element's left edge, y_top at the
        element's top edge (not its vertical center) for a hairline-accurate line.
      - number: int or str, shown inside the circle. Numbering convention:
        keep it stable and sequential per screenshot so the legend table in the
        HTML report can reference "marker N" unambiguously.
      - confirmed: True -> green (field exists in spec), False -> red (gap).

    Returns the same `img` object (mutated) for chaining.
    """
    f = _font(font_size)
    d = ImageDraw.Draw(img)
    for (x, y_top, num, ok) in points:
        color = GREEN if ok else RED
        bg = GREEN_BG if ok else RED_BG
        cy = y_top - connector_len
        r = radius
        d.line([(x, cy + r), (x, y_top)], fill=color, width=2)
        d.ellipse([x - r, cy - r, x + r, cy + r], fill=bg, outline=color, width=2)
        label = str(num)
        tw = d.textlength(label, font=f)
        d.text((x - tw / 2, cy - font_size + 5), label, font=f, fill=color)
    return img


def composite_side_by_side(img_paths, gap=100, bg=(255, 255, 255)):
    """Paste multiple images left-to-right with `gap` px of whitespace between
    them. Returns (composite_image, list_of_x_offsets) so caller can compute
    per-image marker coordinates by adding the right offset.

    Use this when the UI mockup is split across multiple small crops (e.g. two
    separate dropdown-menu screenshots that belong in one figure) rather than
    one full-page capture.
    """
    imgs = [Image.open(p).convert("RGB") for p in img_paths]
    total_w = sum(im.width for im in imgs) + gap * (len(imgs) - 1)
    max_h = max(im.height for im in imgs)
    composite = Image.new("RGB", (total_w, max_h), bg)
    offsets = []
    x = 0
    for im in imgs:
        composite.paste(im, (x, 0))
        offsets.append(x)
        x += im.width + gap
    return composite, offsets


if __name__ == "__main__":
    # Tiny self-test: a blank canvas with one confirmed and one gap marker.
    img = Image.new("RGB", (300, 150), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((20, 60), "confirmed field", fill=(0, 0, 0))
    d.text((20, 100), "missing field", fill=(0, 0, 0))
    mark_points(img, [(10, 60, 1, True), (10, 100, 2, False)])
    out = "/tmp/mockup-api-mapping-selftest.png"
    img.save(out)
    print(f"self-test written to {out}")
