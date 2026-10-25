"""Create a spiral Droste image via complex log -> rotate/scale -> exp.

Run: py -3.11 create_escher.py
Requires: Pillow >= 10.1 and NumPy >= 1.24.
Defaults are calibrated to demo2_nested_quarter.png, not arbitrary images.
See ESCHER.md for the mathematics, coordinate convention, and options.
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

DIRECTORY = Path(__file__).resolve().parent
TAU = 2 * math.pi


def spiral_coefficients(ratio, turns):
    """Return forward and inverse complex multipliers in the log plane.

    a = 1 - i*n*log(ratio)/(2*pi); c = 1/a.
    c maps the source period n*log(ratio) + 2*pi*i to 2*pi*i.
    Thus a complete output revolution has no angular branch seam.
    """
    if not math.isfinite(ratio) or ratio <= 1:
        raise ValueError('The outer/inner scale ratio must be finite and > 1.')
    if not isinstance(turns, int):
        raise ValueError('turns must be an integer for angular closure.')
    inverse = complex(1, -turns * math.log(ratio) / TAU)
    return 1 / inverse, inverse


class PeriodicSource:
    """Extend a recursive source infinitely using its rectangular repeat shell.

    Coordinates use pixel edges: pixel (x, y) has center (x+.5, y+.5).
    Complex imaginary coordinates point up, opposite raster y coordinates.
    Every sample is folded into the original rectangle outside its inner copy;
    this avoids missing pixels and low-resolution deep copies near the center.
    """

    def __init__(self, image, center, ratio):
        if not math.isfinite(ratio) or ratio <= 1:
            raise ValueError('ratio must be finite and > 1.')
        self.pixels = np.asarray(image.convert('RGB'))
        self.height, self.width = self.pixels.shape[:2]
        try:
            self.cx, self.cy = map(float, center)
        except (TypeError, ValueError) as error:
            raise ValueError('Center must contain two numeric coordinates.') from error
        if not (0 < self.cx < self.width and 0 < self.cy < self.height):
            raise ValueError('The recursion fixed point must lie inside the image.')
        self.period = math.log(ratio)
        self.reference_radius = self.width

    def sample_pixels(self, x, y):
        """Bilinear interpolation with pixel-edge coordinates as input."""
        x = np.clip(x - 0.5, 0, self.width - 1)
        y = np.clip(y - 0.5, 0, self.height - 1)
        x0, y0 = np.floor(x).astype(np.intp), np.floor(y).astype(np.intp)
        x1, y1 = np.minimum(x0 + 1, self.width - 1), np.minimum(y0 + 1, self.height - 1)
        fx, fy = (x - x0)[..., None], (y - y0)[..., None]
        upper = self.pixels[y0, x0] * (1-fx) + self.pixels[y0, x1] * fx
        lower = self.pixels[y1, x0] * (1-fx) + self.pixels[y1, x1] * fx
        return upper * (1-fy) + lower * fy

    def sample_log(self, u, theta):
        """Evaluate F(exp(u+i*theta)), with exact log-radius periodicity."""
        theta = np.remainder(theta + math.pi, TAU) - math.pi
        cos_theta, sin_theta = np.cos(theta), np.sin(theta)
        # Ray distance to the outer rectangle from the self-similarity center.
        rx = np.where(cos_theta >= 0, self.width-self.cx, self.cx) / np.maximum(np.abs(cos_theta), 1e-15)
        ry = np.where(sin_theta >= 0, self.cy, self.height-self.cy) / np.maximum(np.abs(sin_theta), 1e-15)
        boundary_radius = np.minimum(rx, ry)
        boundary_u = np.log(boundary_radius / self.reference_radius)
        # Keep boundary/radius in [1, ratio). exp is the antilog step.
        radial_offset = np.remainder(boundary_u - u, self.period)
        radius = boundary_radius * np.exp(-radial_offset)
        return self.sample_pixels(self.cx + radius*cos_theta,
                                  self.cy - radius*sin_theta)


def render(source, size, coordinate_map, inverse=1+0j, samples=2,
           phase=0.0, rotation=0.0, log_offset=0j):
    """Inverse-map the continuous function, not an already-rasterized stage.

    Using identical coordinates for stage 2 and stage 3 is mathematically the
    same pipeline, without extra blur from rotating a finite log-image bitmap.
    Supersampling and bilinear interpolation soften minification artifacts;
    this is not analytic antialiasing at the central logarithmic singularity.
    """
    output = np.empty((size, size, 3), dtype=np.uint8)
    source_offset = inverse * log_offset
    offsets = (np.arange(samples) + 0.5) / samples
    row_block = 32
    for start in range(0, size, row_block):
        end = min(start + row_block, size)
        accumulation = np.zeros((end-start, size, 3), dtype=np.float32)
        for oy in offsets:
            y = (np.arange(start, end, dtype=np.float64) + oy)[:, None]
            for ox in offsets:
                x = (np.arange(size, dtype=np.float64) + ox)[None, :]
                u, theta = coordinate_map(x, y)
                source_u = inverse.real*u - inverse.imag*theta + phase*source.period + source_offset.real
                source_theta = inverse.imag*u + inverse.real*theta + rotation + source_offset.imag
                accumulation += source.sample_log(source_u, source_theta)
        output[start:end] = np.uint8(np.clip(np.rint(accumulation / samples**2), 0, 255))
    return Image.fromarray(output)


def log_coordinates(size):
    """Square log-plane window: real in [-2*pi, 0], imaginary in [-pi, pi]."""
    def coordinates(x, y):
        return -TAU + x*TAU/size, math.pi - y*TAU/size
    return coordinates


def cartesian_coordinates(size, center_fraction):
    """log((z-p)/R), with R=image width and p=the recursion fixed point."""
    cx, cy = center_fraction[0]*size, center_fraction[1]*size
    def coordinates(x, y):
        dx, dy = x-cx, cy-y
        radius = np.maximum(np.hypot(dx, dy), 1e-12)
        return np.log(radius / size), np.arctan2(dy, dx)
    return coordinates


def save_contact_sheet(images, destination, tile_size=512):
    """Save the four pipeline stages in a labeled 2x2 grid."""
    label_height = max(36, tile_size//32)
    sheet = Image.new('RGB', (tile_size*2, (tile_size+label_height)*2), '#eeeeee')
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=max(20, label_height//2))
    for index, (label, image) in enumerate(images):
        x = (index % 2)*tile_size
        y = (index // 2)*(tile_size+label_height)
        draw.text((x+10, y+6), label, fill='black', font=font)
        sheet.paste(image.resize((tile_size, tile_size), Image.Resampling.LANCZOS),
                    (x, y+label_height))
    sheet.save(destination, quality=94)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=DIRECTORY/'demo2_nested_quarter.png')
    parser.add_argument('--output-dir', type=Path, default=DIRECTORY/'escher_output')
    parser.add_argument('--size', type=int, default=4096, help='Final square image size.')
    parser.add_argument('--log-size', type=int, default=4096, help='Square intermediate size.')
    parser.add_argument('--ratio', type=float, default=4.0, help='Source outer/inner linear ratio.')
    parser.add_argument('--turns', type=int, default=1, help='Integer spiral winding; -1 reverses it, 0 disables it.')
    parser.add_argument('--center', type=float, nargs=2, metavar=('X', 'Y'),
                        help='Source recursion fixed point in pixel-edge coordinates.')
    parser.add_argument('--phase', type=float, default=0.0, help='Source radial phase in repeat periods.')
    parser.add_argument('--rotation-deg', type=float, default=0.0, help='Additional source angular phase.')
    parser.add_argument('--view-rotation-deg', type=float, default=0.0,
                        help='Rigid final-view rotation about the spiral origin; positive is counterclockwise.')
    parser.add_argument('--view-scale', type=float, default=1.0,
                        help='Final-view scale; below 1 zooms out without blank corners.')
    parser.add_argument('--view-offset', type=float, nargs=2, default=(0.0, 0.0), metavar=('X', 'Y'),
                        help='Final translation as canvas fractions; positive X is right, Y is down.')
    parser.add_argument('--samples', type=int, choices=(1, 2, 4), default=2,
                        help='Samples per pixel axis (2 means four samples/pixel).')
    args = parser.parse_args()
    if args.size < 1 or args.log_size < 1:
        parser.error('Image dimensions must be positive.')
    if not math.isfinite(args.ratio) or args.ratio <= 1:
        parser.error('--ratio must be finite and > 1.')
    if not all(math.isfinite(value) for value in
               (args.phase, args.rotation_deg, args.view_rotation_deg, *args.view_offset)):
        parser.error('Phase, rotation, and view offset must be finite.')
    if not math.isfinite(args.view_scale) or args.view_scale <= 0:
        parser.error('--view-scale must be finite and positive.')
    return args


def main():
    args = parse_args()
    with Image.open(args.input) as opened:
        image = opened.convert('RGB')
    width, height = image.size
    if width != height:
        raise ValueError('This renderer expects a square source image.')
    # Original placement z -> t+z/4 has fixed point p=t/(1-1/4), NOT frame center.
    center = args.center
    if center is None:
        center = (2287*width/4096/(1-1/args.ratio),
                  537*height/4096/(1-1/args.ratio))
    source = PeriodicSource(image, center, args.ratio)
    forward, inverse = spiral_coefficients(args.ratio, args.turns)
    rotation = math.radians(args.rotation_deg)
    # Inverse of z_view = view_scale * exp(i*beta) * z_spiral.
    view_log_offset = complex(-math.log(args.view_scale), -math.radians(args.view_rotation_deg))
    output_center = (center[0]/width + args.view_offset[0],
                     center[1]/height + args.view_offset[1])
    output_dir = args.output_dir.resolve()
    names = ('01_log_polar.png', '02_rotated_log.png', '03_escher.png',
             '04_transformation_grid.png')
    if args.input.resolve() in {output_dir/name for name in names}:
        raise ValueError('Input must not be one of the output paths.')
    output_dir.mkdir(parents=True, exist_ok=True)

    print('Rendering 1/3: complex-log plane...', flush=True)
    log_image = render(source, args.log_size, log_coordinates(args.log_size),
                       samples=args.samples, phase=args.phase, rotation=rotation)
    log_image.save(output_dir/names[0])

    print('Rendering 2/3: rotated/scaled complex-log plane...', flush=True)
    rotated_image = render(source, args.log_size, log_coordinates(args.log_size),
                           inverse=inverse, samples=args.samples,
                           phase=args.phase, rotation=rotation, log_offset=view_log_offset)
    rotated_image.save(output_dir/names[1])

    print('Rendering 3/3: exponential back to the image plane...', flush=True)
    final = render(source, args.size, cartesian_coordinates(args.size, output_center),
                   inverse=inverse, samples=args.samples,
                   phase=args.phase, rotation=rotation, log_offset=view_log_offset)
    final.save(output_dir/names[2])
    final.resize((1024, 1024), Image.Resampling.LANCZOS).save(output_dir/'preview.jpg', quality=95)
    stages = [
        ('Original image', image), ('1. Complex log', log_image),
        ('2. Rotated/scaled log', rotated_image), ('3. Exponential: spiral Droste', final),
    ]
    save_contact_sheet(stages, output_dir/names[3], tile_size=2048)
    save_contact_sheet(stages, output_dir/'stages.jpg')

    details = {
        'input': str(args.input.resolve()),
        'input_size': list(image.size),
        'final_size': [args.size, args.size],
        'log_image_size': [args.log_size, args.log_size],
        'source_outer_inner_ratio': args.ratio,
        'fixed_point_pixel_edges': list(center),
        'log_reference_radius': source.reference_radius,
        'log_window': {'real': [-TAU, 0], 'imaginary': [-math.pi, math.pi]},
        'turns': args.turns,
        'forward_log_multiplier': [forward.real, forward.imag],
        'inverse_log_multiplier': [inverse.real, inverse.imag],
        'log_rotation_degrees': math.degrees(math.atan2(forward.imag, forward.real)),
        'log_scale_correction': abs(forward),
        'spiral_repeat_scale': math.exp(forward.real*source.period),
        'spiral_repeat_rotation_degrees': math.degrees(forward.imag*source.period),
        'phase_periods': args.phase,
        'source_rotation_degrees': args.rotation_deg,
        'view_rotation_degrees': args.view_rotation_deg,
        'view_scale': args.view_scale,
        'view_offset_canvas_fractions': list(args.view_offset),
        'output_fixed_point_pixels': [value*args.size for value in output_center],
        'samples_per_pixel': args.samples**2,
        'pipeline': 'log(z) -> c*log(z) -> exp(c*log(z)); rendered by inverse mapping',
        'periodic_extension': 'Samples fold into the rectangular outer-minus-inner source shell.',
    }
    (output_dir/'parameters.json').write_text(json.dumps(details, indent=2)+'\n', encoding='utf-8')
    print(f'Saved all stages to: {output_dir}')
    print(f'Log-plane rotation: {details["log_rotation_degrees"]:.6f} degrees')
    print(f'Log-plane scale correction: {abs(forward):.8f}')


if __name__ == '__main__':
    main()
