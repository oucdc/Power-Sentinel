"""Generate the application icon (run once at build time)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "notebook_power_monitor" / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)


def make_icon(size: int = 512) -> Image.Image:
    scale = size / 512.0
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(
        (14 * scale, 14 * scale, 498 * scale, 498 * scale),
        radius=112 * scale,
        fill=(9, 20, 32, 255),
        outline=(34, 76, 98, 255),
        width=max(2, int(7 * scale)),
    )
    # soft cyan ring
    d.ellipse(
        (66 * scale, 66 * scale, 446 * scale, 446 * scale),
        outline=(18, 57, 76, 255),
        width=max(1, int(3 * scale)),
    )
    bolt = [
        (296, 72),
        (124, 288),
        (232, 288),
        (198, 440),
        (390, 222),
        (272, 222),
    ]
    bolt = [(x * scale, y * scale) for x, y in bolt]
    d.polygon(bolt, fill=(77, 216, 255, 255))
    # highlight on the upper half
    highlight = [
        (296, 72),
        (124, 288),
        (232, 288),
        (222, 341),
        (174, 235),
    ]
    highlight = [(x * scale, y * scale) for x, y in highlight]
    d.polygon(highlight, fill=(173, 240, 255, 255))
    # live status dot
    d.ellipse(
        (382 * scale, 382 * scale, 438 * scale, 438 * scale),
        fill=(10, 28, 29, 255),
        outline=(11, 20, 32, 255),
        width=max(2, int(8 * scale)),
    )
    d.ellipse(
        (393 * scale, 393 * scale, 427 * scale, 427 * scale),
        fill=(91, 224, 160, 255),
    )
    return img


def main() -> None:
    img = make_icon(512)
    img.save(ASSETS / "icon-512.png")
    img.save(
        ASSETS / "app.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(ASSETS / "app.ico")
    print(ASSETS / "icon-512.png")


if __name__ == "__main__":
    main()
