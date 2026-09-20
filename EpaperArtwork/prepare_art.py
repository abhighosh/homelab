"""Prepare a reviewed raster illustration for the E1001's four-gray display."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps


SIZE = (800, 480)
LEVELS = (0, 85, 170, 255)


def prepare(source: Path, destination: Path, *, crop: bool = False, strengthen_lines: bool = False) -> None:
    with Image.open(source) as original:
        grayscale = ImageOps.exif_transpose(original).convert("L")
        if crop:
            canvas = ImageOps.fit(grayscale, SIZE, method=Image.Resampling.LANCZOS)
        else:
            canvas = ImageOps.pad(grayscale, SIZE, color=255, method=Image.Resampling.LANCZOS)
    if strengthen_lines:
        canvas = canvas.filter(ImageFilter.MinFilter(3))

    prepared = quantize_four_tone(canvas)
    destination.parent.mkdir(parents=True, exist_ok=True)
    prepared.save(destination, format="PNG", optimize=True)


def quantize_four_tone(canvas: Image.Image) -> Image.Image:
    """Explicit four-tone Floyd–Steinberg diffusion for an in-memory image."""
    if canvas.size != SIZE:
        raise ValueError(f"Expected {SIZE} image, got {canvas.size}")

    # Explicit four-tone Floyd–Steinberg diffusion. Pillow's palette quantizer
    # may select duplicate palette entries and erase fine architectural detail.
    width, height = SIZE
    values = [float(value) for value in canvas.getdata()]
    result = bytearray(width * height)
    for y in range(height):
        for x in range(width):
            index = y * width + x
            old = min(255.0, max(0.0, values[index]))
            new = LEVELS[min(3, int((old + 42.5) // 85))]
            result[index] = new
            error = old - new
            if x + 1 < width:
                values[index + 1] += error * 7 / 16
            if y + 1 < height:
                if x > 0:
                    values[index + width - 1] += error * 3 / 16
                values[index + width] += error * 5 / 16
                if x + 1 < width:
                    values[index + width + 1] += error / 16
    return Image.frombytes("L", SIZE, bytes(result))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--crop", action="store_true", help="Fill the screen, cropping edges if needed")
    parser.add_argument("--strengthen-lines", action="store_true", help="Darken thin ink lines after scaling")
    args = parser.parse_args()
    if args.source.resolve() == args.destination.resolve():
        parser.error("source and destination must differ")
    prepare(args.source, args.destination, crop=args.crop, strengthen_lines=args.strengthen_lines)


if __name__ == "__main__":
    main()
