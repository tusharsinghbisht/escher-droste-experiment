"""Undo create_escher.py's complex-log spiral using its saved parameters.

Run: .venv/Scripts/python.exe revert_escher.py
The original pre-spiral image is NOT read unless --reference is supplied,
and then it is used only for comparison, never for reconstruction.
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from create_escher import (
    TAU,
    PeriodicSource,
    log_coordinates,
    save_contact_sheet,
    spiral_coefficients,
)

DIRECTORY = Path(__file__).resolve().parent


def numeric_vector(value, length, name):
    """Validate metadata without silently accepting malformed dimensions."""
    try:
        result = tuple(float(component) for component in value)
    except (TypeError, ValueError) as error:
        raise ValueError(f'{name} must contain {length} numeric values.') from error
    if len(result) != length or not all(math.isfinite(component) for component in result):
        raise ValueError(f'{name} must contain {length} finite values.')
    return result


def finite_number(value, name):
    """Read a scalar metadata setting, reporting invalid input clearly."""
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f'{name} must be numeric.') from error
    if not math.isfinite(number):
        raise ValueError(f'{name} must be finite.')
    return number


class InverseModel:
    """Coordinate inverse, including source phase and rigid final-view changes."""

    def __init__(self, parameters):
        self.source_size = numeric_vector(parameters['input_size'], 2, 'input_size')
        self.final_size = numeric_vector(parameters['final_size'], 2, 'final_size')
        if min(*self.source_size, *self.final_size) <= 0:
            raise ValueError('Image dimensions must be positive.')
        self.source_center = numeric_vector(parameters['fixed_point_pixel_edges'], 2, 'fixed point')
        self.ratio = finite_number(parameters['source_outer_inner_ratio'], 'ratio')
        forward, _ = spiral_coefficients(self.ratio, parameters.get('turns', 1))
        if 'forward_log_multiplier' in parameters:
            real, imaginary = numeric_vector(parameters['forward_log_multiplier'], 2, 'forward multiplier')
            forward = complex(real, imaginary)
        if forward.real <= 0 or abs(forward) < 1e-12:
            raise ValueError('Forward multiplier must have a positive real part.')
        self.forward = forward
        self.period = forward*math.log(self.ratio)
        self.source_radius = finite_number(parameters.get('log_reference_radius', self.source_size[0]), 'radius')
        scale = finite_number(parameters.get('view_scale', 1.0), 'view scale')
        angle = finite_number(parameters.get('view_rotation_degrees', 0.0), 'view angle')
        phase = finite_number(parameters.get('phase_periods', 0.0), 'phase')
        rotation = finite_number(parameters.get('source_rotation_degrees', 0.0), 'source angle')
        if scale <= 0 or self.source_radius <= 0 or not all(
            math.isfinite(value) for value in (scale, angle, phase, rotation, self.source_radius)
        ):
            raise ValueError('Scale/radius must be positive and all transform settings finite.')
        self.source_phase = complex(phase*math.log(self.ratio), math.radians(rotation))
        self.view_offset = complex(-math.log(scale), -math.radians(angle))
        offset = numeric_vector(parameters.get('view_offset_canvas_fractions', (0, 0)), 2, 'view offset')
        default_center = tuple(
            (self.source_center[index]/self.source_size[index]+offset[index])*self.final_size[index]
            for index in range(2)
        )
        self.final_center = numeric_vector(parameters.get('output_fixed_point_pixels', default_center), 2, 'output fixed point')
        if not all(0 < self.final_center[index] < self.final_size[index] for index in range(2)):
            raise ValueError('The spiral origin must lie inside its registered image.')

    def source_to_spiral_log(self, u, theta):
        # Forward coordinate map is the sampling map of an inverse image warp.
        # J(w) = F(a*(w+d)+q), so F(v) = J(c*(v-q)-d).
        value = self.forward*(u+1j*theta-self.source_phase)-self.view_offset
        return value.real, value.imag


class SpiralRaster:
    """Sample only the supplied spiral raster, optionally using its repeats.

    The largest in-frame equivalent repeat is preferred for better resolution.
    Missing samples are gray, NOT edge-clamped or filled from the original.
    """

    def __init__(self, image, model, repeat=True):
        self.model, self.repeat = model, repeat
        self.width, self.height = image.size
        registered_width, registered_height = model.final_size
        self.sx = self.width/registered_width
        self.sy = self.height/registered_height
        cx, cy = model.final_center
        self.raster = PeriodicSource(image, (cx*self.sx, cy*self.sy), model.ratio)
        # Bounds at pixel centers, expressed in the registered spiral coordinates.
        self.bounds = (0.5/self.sx, 0.5/self.sy,
                       registered_width-0.5/self.sx, registered_height-0.5/self.sy)
        left, top, right, bottom = self.bounds
        minimum_radius = min(cx-left, right-cx, cy-top, bottom-cy)
        if minimum_radius <= 0:
            raise ValueError('The origin must be at least half a raster pixel inside the image.')
        maximum_radius = max(math.hypot(x-cx, y-cy) for x in (left, right) for y in (top, bottom))
        self.maximum_u = math.log(maximum_radius/registered_width)
        self.candidate_count = math.ceil(math.log(maximum_radius/minimum_radius)/model.period.real)+3
        if self.candidate_count > 1024:
            raise ValueError('Repeat ratio too close to 1 for practical branch selection.')

    def sample_log(self, u, theta):
        u, theta = np.broadcast_arrays(u, theta)
        chosen_x, chosen_y = np.zeros_like(u), np.zeros_like(u)
        found = np.zeros(u.shape, dtype=bool)
        model = self.model
        if self.repeat:
            first = np.floor((self.maximum_u-u)/model.period.real)
        else:
            first = np.zeros_like(u)
        left, top, right, bottom = self.bounds
        for step in range(self.candidate_count if self.repeat else 1):
            winding = first-step
            radius = model.final_size[0]*np.exp(np.clip(u+winding*model.period.real, -700, 700))
            angle = np.remainder(theta+winding*model.period.imag+math.pi, TAU)-math.pi
            x = model.final_center[0]+radius*np.cos(angle)
            y = model.final_center[1]-radius*np.sin(angle)
            valid = (x >= left) & (x <= right) & (y >= top) & (y <= bottom) & ~found
            chosen_x[valid], chosen_y[valid] = x[valid], y[valid]
            found |= valid
            if found.all():
                break
        colors = self.raster.sample_pixels(chosen_x*self.sx, chosen_y*self.sy)
        return np.where(found[..., None], colors, 224.0), found


def render_inverse(source, dimensions, coordinate_map, transform=None, samples=2):
    """Inverse-resample a log or Cartesian view in bounded row blocks."""
    width, height = dimensions
    result = np.empty((height, width, 3), dtype=np.uint8)
    coverage = np.empty((height, width), dtype=np.uint8)
    offsets = (np.arange(samples)+0.5)/samples
    for start in range(0, height, 32):
        end = min(start+32, height)
        accumulated = np.zeros((end-start, width, 3), dtype=np.float64)
        valid_samples = np.zeros((end-start, width), dtype=np.float64)
        for oy in offsets:
            y = (np.arange(start, end, dtype=np.float64)+oy)[:, None]
            for ox in offsets:
                x = (np.arange(width, dtype=np.float64)+ox)[None, :]
                u, theta = coordinate_map(x, y)
                if transform is not None:
                    u, theta = transform(u, theta)
                colors, valid = source.sample_log(u, theta)
                accumulated += colors
                valid_samples += valid
        result[start:end] = np.uint8(np.clip(np.rint(accumulated/samples**2), 0, 255))
        coverage[start:end] = np.uint8(np.rint(255*valid_samples/samples**2))
    return Image.fromarray(result), Image.fromarray(coverage)


def reconstruction_coordinates(model, width, height):
    """Coordinates of the requested pre-spiral canvas at its original aspect."""
    def coordinates(x, y):
        dx = x*model.source_size[0]/width-model.source_center[0]
        dy = model.source_center[1]-y*model.source_size[1]/height
        return np.log(np.maximum(np.hypot(dx, dy), 1e-12)/model.source_radius), np.arctan2(dy, dx)
    return coordinates


def compare_reference(reference, recovered, destination):
    """Comparison only: the reference never contributes to recovered pixels."""
    expected = reference.convert('RGB').resize((1024, 1024), Image.Resampling.LANCZOS)
    actual = recovered.resize((1024, 1024), Image.Resampling.LANCZOS)
    difference = np.asarray(expected, dtype=np.float32)-np.asarray(actual, dtype=np.float32)
    mse = np.mean(difference**2).item()
    amplified = Image.fromarray(np.uint8(np.clip(np.abs(difference)*4, 0, 255)))
    save_contact_sheet([
        ('Reference (comparison only)', expected), ('Recovered from spiral', actual),
        ('Absolute error x4', amplified), ('Recovered detail', actual),
    ], destination)
    return {'comparison_size': [1024, 1024], 'mean_absolute_rgb_error': np.mean(np.abs(difference)).item(),
            'psnr_db': 10*math.log10(255**2/mse) if mse else None}


def run_inverse(input_path, parameters, output_dir, size=4096, log_size=None,
                samples=2, repeat=True, reference_path=None):
    """Save inverse stages using only the spiral and its numeric metadata."""
    if size < 1 or (log_size is not None and log_size < 1) or samples not in (1, 2, 4):
        raise ValueError('Sizes must be positive and samples must be 1, 2, or 4.')
    log_size = log_size or size
    model = InverseModel(parameters)
    with Image.open(input_path) as opened:
        image = opened.convert('RGB')
    source = SpiralRaster(image, model, repeat)
    output_dir = Path(output_dir)
    names = ('01_spiral_log.png', '02_unrotated_log.png', '03_reverted.png', '04_inverse_grid.png')
    if Path(input_path).resolve() in {(output_dir/name).resolve() for name in names}:
        raise ValueError('Input must not be overwritten by an output.')
    output_dir.mkdir(parents=True, exist_ok=True)
    print('Inverse 1/3: unwrapping the supplied spiral...', flush=True)
    unwrapped, _ = render_inverse(source, (log_size, log_size), log_coordinates(log_size), samples=samples)
    unwrapped.save(output_dir/names[0])
    print('Inverse 2/3: undoing log rotation, scale, and phases...', flush=True)
    corrected, _ = render_inverse(source, (log_size, log_size), log_coordinates(log_size),
                                  model.source_to_spiral_log, samples)
    corrected.save(output_dir/names[1])
    dimensions = (size, max(1, round(size*model.source_size[1]/model.source_size[0])))
    print('Inverse 3/3: reconstructing the pre-spiral image...', flush=True)
    recovered, coverage = render_inverse(source, dimensions, reconstruction_coordinates(model, *dimensions),
                                         model.source_to_spiral_log, samples)
    recovered.save(output_dir/names[2])
    coverage.save(output_dir/'coverage.png')
    stages = [('Supplied spiral', image), ('1. Spiral log plane', unwrapped),
              ('2. Unrotated log plane', corrected), ('3. Recovered pre-spiral image', recovered)]
    save_contact_sheet(stages, output_dir/names[3], tile_size=2048)
    save_contact_sheet(stages, output_dir/'stages.jpg')
    recovered.resize((1024, round(1024*dimensions[1]/dimensions[0])), Image.Resampling.LANCZOS).save(
        output_dir/'preview.jpg', quality=95)
    report = {'spiral_input': str(Path(input_path).resolve()), 'output_size': list(dimensions),
              'repeat_extension': repeat, 'samples_per_pixel': samples**2,
              'raster_coverage_fraction': np.asarray(coverage, dtype=np.float32).mean().item()/255,
              'original_image_used_for_reconstruction': False,
              'formula': 'w_spiral = c*(w_source-q)-d; sample supplied spiral at exp(w_spiral)',
              'limitations': 'Raster resampling is lossy; blank artwork regions and nonperiodic source data cannot be recovered exactly.'}
    if reference_path is not None:
        with Image.open(reference_path) as reference:
            report['reference_comparison'] = compare_reference(reference, recovered, output_dir/'reference_comparison.jpg')
    (output_dir/'inverse_report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(f'Saved inverse experiment to {output_dir.resolve()}')
    return recovered, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=DIRECTORY/'escher_output/03_escher.png')
    parser.add_argument('--parameters', type=Path, default=DIRECTORY/'escher_output/parameters.json')
    parser.add_argument('--output-dir', type=Path, default=DIRECTORY/'reverted_output')
    parser.add_argument('--size', type=int, default=4096)
    parser.add_argument('--log-size', type=int)
    parser.add_argument('--samples', type=int, choices=(1, 2, 4), default=2)
    parser.add_argument('--no-repeat', action='store_true', help='Literal warp: leave out-of-frame areas gray instead of sampling equivalent repeats.')
    parser.add_argument('--reference', type=Path, help='Optional original for comparison ONLY; never used to recover pixels.')
    args = parser.parse_args()
    try:
        parameters = json.loads(args.parameters.read_text(encoding='utf-8'))
        run_inverse(args.input, parameters, args.output_dir, args.size, args.log_size,
                    args.samples, not args.no_repeat, args.reference)
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
        parser.exit(2, f'Inverse transform failed: {error}\n')


if __name__ == '__main__':
    main()
