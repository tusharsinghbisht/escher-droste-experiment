"""Recreate demo2's nested-frame image with an exact 1/4 linear scale.

Run on Windows:
    py -3.11 create_nested.py

Dependencies:
    py -3.11 -m pip install Pillow numpy

Input: demo2.png (1254 x 1254), beside this script.
Output: demo2_nested_quarter.png (4096 x 4096).

The inner frame opening, excluding its black border, is exactly 1024 x 1024.
Frame and wall coordinates are calibrated specifically for demo2.png; this is
not an automatic frame detector for arbitrary photographs. Originals are kept.
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

DIRECTORY = Path(__file__).resolve().parent
IMAGE_SIZE = 4096
OPENING_SIZE = IMAGE_SIZE // 4
OPENING = (2287, 537, 3311, 1561)
LEVELS = 6  # Nested widths: 1024, 256, 64, 16, 4, 1 pixels.


def wall_features(x, y):
    """Cubic lighting model in the original image's coordinate system."""
    x = (x - 860) / 350
    y = (y - 330) / 350
    return np.stack(
        [np.ones_like(x), x, y, x*x, x*y, y*y,
         x*x*x, x*x*y, x*y*y, y*y*y],
        axis=-1,
    )


def restore_wall(base, reference):
    """Remove the old, larger frame using nearby wall lighting and texture."""
    pixels = np.asarray(reference, dtype=np.float64)
    clean_wall = [
        (540, 5, 1160, 65),
        (550, 85, 603, 290),
        (585, 290, 603, 400),
        (1120, 85, 1160, 495),
        (630, 585, 900, 650),
    ]
    sample_features, sample_colors = [], []
    for left, top, right, bottom in clean_wall:
        yy, xx = np.mgrid[top:bottom:3, left:right:3]
        sample_features.append(wall_features(xx, yy).reshape(-1, 10))
        sample_colors.append(pixels[top:bottom:3, left:right:3].reshape(-1, 3))
    coefficients = np.linalg.lstsq(
        np.concatenate(sample_features), np.concatenate(sample_colors), rcond=None
    )[0]

    roi = (1940, 195, 3690, 1935)
    left, top, right, bottom = roi
    yy, xx = np.mgrid[top:bottom, left:right]
    wall = wall_features(xx * 1254 / IMAGE_SIZE, yy * 1254 / IMAGE_SIZE) @ coefficients

    # Remove lighting from a real wall sample, then mirror-tile its fine texture.
    patch = reference.crop((650, 585, 900, 650))
    texture = (
        np.asarray(patch, dtype=np.float64)
        - np.asarray(patch.filter(ImageFilter.GaussianBlur(3)), dtype=np.float64)
    )
    texture_image = Image.fromarray(np.uint8(np.clip(texture + 128, 0, 255)))
    texture_image = texture_image.resize((817, 212), Image.Resampling.LANCZOS)
    tile = np.asarray(texture_image, dtype=np.float64) - 128
    tile = np.concatenate((tile, tile[:, ::-1]), axis=1)
    tile = np.concatenate((tile, tile[::-1]), axis=0)
    texture = np.tile(
        tile,
        ((bottom-top)//tile.shape[0]+1, (right-left)//tile.shape[1]+1, 1),
    )[:bottom-top, :right-left]
    wall_image = Image.fromarray(np.uint8(np.clip(wall + texture, 0, 255)))

    # Feather beyond the old frame and its shadow without changing nearby objects.
    mask = Image.new('L', wall_image.size)
    ImageDraw.Draw(mask).rectangle(
        (1982-left, 237-top, 3635-left, 1880-top), fill=255
    )
    mask = mask.filter(ImageFilter.GaussianBlur(10))
    restored = base.copy()
    restored.paste(wall_image, roi[:2], mask)
    return restored


def resize_frame(base, restored):
    """Nine-slice the existing border around an exact 1024 x 1024 opening."""
    source_x = (2002, 2133, 3465, 3595)
    source_y = (258, 393, 1706, 1840)
    target_x = (2186, OPENING[0], OPENING[2], 3411)
    target_y = (432, OPENING[1], OPENING[3], 1666)

    shadow = Image.new('L', base.size)
    ImageDraw.Draw(shadow).rectangle(
        (target_x[0]+17, target_y[0]+17, target_x[-1]+17, target_y[-1]+17),
        fill=34,
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(7))
    restored = Image.composite(Image.new('RGB', base.size, (0, 0, 0)), restored, shadow)

    # Resample border sections independently so rounding cannot alter the opening.
    for row in range(3):
        for col in range(3):
            patch = base.crop(
                (source_x[col], source_y[row], source_x[col+1], source_y[row+1])
            )
            size = (target_x[col+1]-target_x[col], target_y[row+1]-target_y[row])
            restored.paste(
                patch.resize(size, Image.Resampling.LANCZOS),
                (target_x[col], target_y[row]),
            )
    return restored


def main():
    with Image.open(DIRECTORY / 'demo2.png') as source:
        reference = source.convert('RGB')
    if reference.size != (1254, 1254):
        raise ValueError('This script requires the original 1254 x 1254 demo2.png.')

    # Resize directly from the original, making this script independently repeatable.
    base = reference.resize((IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.LANCZOS)
    scene = resize_frame(base, restore_wall(base, reference))
    if OPENING[2]-OPENING[0] != OPENING_SIZE or OPENING[3]-OPENING[1] != OPENING_SIZE:
        raise ValueError('Frame opening must be exactly one quarter of the image.')

    nested = scene.copy()
    for _ in range(LEVELS):
        inset = nested.resize((OPENING_SIZE, OPENING_SIZE), Image.Resampling.LANCZOS)
        composed = scene.copy()
        composed.paste(inset, OPENING[:2])
        nested = composed

    destination = DIRECTORY / 'demo2_nested_quarter.png'
    nested.save(destination)
    with Image.open(destination) as check:
        if check.size != (IMAGE_SIZE, IMAGE_SIZE):
            raise ValueError('Output dimensions are incorrect.')
        check.verify()
    print(f'Saved: {destination}')
    print(f'Image: {IMAGE_SIZE} x {IMAGE_SIZE} px')
    print(f'Inner opening: {OPENING_SIZE} x {OPENING_SIZE} px (exactly 1/4 per dimension)')
    print('Nested sizes: 1024, 256, 64, 16, 4, 1 pixels')


if __name__ == '__main__':
    main()
