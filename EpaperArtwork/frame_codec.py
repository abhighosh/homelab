"""Seeed E1001 Gray4 wire format: two 2-bit levels in each byte's nibbles."""

from __future__ import annotations

from PIL import Image

from render_screens import SIZE, validate


FRAME_BYTES = SIZE[0] * SIZE[1] // 2


def pack_gray4(image: Image.Image) -> bytes:
    validate(image, "wire frame")
    pixels = image.tobytes()
    # The Seeed_GFX example places the left pixel in the high nibble, right
    # pixel in the low nibble, using palette indices 0..3.
    return bytes(((pixels[i] // 85) << 4) | (pixels[i + 1] // 85)
                 for i in range(0, len(pixels), 2))
