#!/usr/bin/env python3
"""Generate the WinIso-NG logo: a compact disc on a light rounded tile.

Run from the repository root:

    python3 packaging/make_logo.py

It writes src/WinIso/data/winiso-logo.png, src/WinIso/data/icon.ico and
.github/winiso-logo.png.
"""

import os

from PIL import Image, ImageDraw, ImageFilter

SIZE = 1024
OUTPUTS = [
    ("src/WinIso/data/winiso-logo.png", 512),
    (".github/winiso-logo.png", 512),
    ("doc/logo.png", 512),
]

WHITE = (255, 255, 255, 255)
BORDER = (226, 232, 240, 255)
SLATE = (100, 116, 139, 255)
BLUE = (37, 99, 235, 255)
BLUE_DARK = (29, 78, 216, 255)
TEAL = (13, 148, 136, 255)
VIOLET = (99, 102, 241, 255)


def lerp(first, second, ratio):
    ratio = max(0.0, min(1.0, ratio))
    return tuple(int(a + (b - a) * ratio) for a, b in zip(first, second))


def disc(size):
    """Draw the CD with concentric rings and a soft specular highlight."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")

    centre = size / 2.0
    outer = size * 0.37
    hole = size * 0.058

    # Disc body: silver, brighter towards the centre, darker at the rim.
    steps = int(outer)
    for index in range(steps, 0, -1):
        ratio = index / outer
        if ratio > 0.90:
            colour = lerp((203, 213, 225), (226, 232, 240), (ratio - 0.90) / 0.10)
        elif ratio > 0.62:
            colour = lerp((226, 232, 240), (241, 245, 249), (ratio - 0.62) / 0.28)
        elif ratio > 0.30:
            colour = lerp((241, 245, 249), (255, 255, 255), (ratio - 0.30) / 0.32)
        else:
            colour = lerp((255, 255, 255), (219, 234, 254), ratio / 0.30)

        draw.ellipse(
            [centre - index, centre - index, centre + index, centre + index],
            fill=colour + (255,),
        )

    # Data surface: concentric rings in the brand colours, like light on a CD.
    for ratio, colour, alpha, width_ratio in (
        (0.88, (255, 255, 255), 210, 0.010),
        (0.76, SLATE, 120, 0.004),
        (0.67, BLUE, 190, 0.014),
        (0.59, TEAL, 150, 0.009),
        (0.51, VIOLET, 120, 0.007),
        (0.43, BLUE_DARK, 140, 0.006),
        (0.35, SLATE, 90, 0.004),
    ):
        radius = outer * ratio
        draw.ellipse(
            [centre - radius, centre - radius, centre + radius, centre + radius],
            outline=colour[:3] + (alpha,), width=max(2, int(size * width_ratio)),
        )

    # Soft sheen on the upper-left half of the disc.
    sheen = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sheen_draw = ImageDraw.Draw(sheen, "RGBA")
    sheen_draw.ellipse(
        [centre - outer * 1.25, centre - outer * 1.45, centre + outer * 0.85, centre + outer * 0.65],
        fill=(255, 255, 255, 90),
    )
    disc_mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(disc_mask).ellipse(
        [centre - outer, centre - outer, centre + outer, centre + outer], fill=255
    )
    sheen.putalpha(Image.composite(sheen.getchannel("A"), Image.new("L", (size, size), 0), disc_mask))
    image = Image.alpha_composite(image, sheen.filter(ImageFilter.GaussianBlur(size * 0.02)))

    draw = ImageDraw.Draw(image, "RGBA")

    # Rim and centre hole.
    draw.ellipse(
        [centre - outer, centre - outer, centre + outer, centre + outer],
        outline=(226, 232, 240, 235), width=max(3, int(size * 0.008)),
    )
    draw.ellipse(
        [centre - hole, centre - hole, centre + hole, centre + hole],
        fill=(37, 99, 235, 255), outline=(255, 255, 255, 220), width=max(2, int(size * 0.004)),
    )
    draw.ellipse(
        [centre - hole * 0.40, centre - hole * 0.40, centre + hole * 0.40, centre + hole * 0.40],
        fill=(29, 78, 216, 255),
    )

    return image


def build(size=SIZE):
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")

    # Rounded tile background with a very light vertical gradient.
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    tile_draw = ImageDraw.Draw(tile, "RGBA")
    for y in range(size):
        ratio = y / size
        tile_draw.line([(0, y), (size, y)], fill=lerp((37, 99, 235), (29, 78, 216), ratio) + (255,))

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [size * 0.03, size * 0.03, size * 0.97, size * 0.97], radius=size * 0.20, fill=255
    )
    image.paste(tile, (0, 0), mask)

    draw.rounded_rectangle(
        [size * 0.03, size * 0.03, size * 0.97, size * 0.97],
        radius=size * 0.20, outline=(30, 64, 175, 255), width=max(2, int(size * 0.004)),
    )

    image = Image.alpha_composite(image, disc(size))
    return image


def main():
    logo = build()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    for relative, width in OUTPUTS:
        path = os.path.join(root, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        logo.resize((width, width), Image.LANCZOS).save(path)
        print("wrote", relative)

    icon_path = os.path.join(root, "src/WinIso/data/icon.ico")
    logo.save(icon_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote src/WinIso/data/icon.ico")


if __name__ == "__main__":
    main()
