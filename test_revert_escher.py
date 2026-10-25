"""Tests for the inverse coordinate map and raster-only reconstruction."""

import math
import unittest

import numpy as np
from PIL import Image

from create_escher import (
    PeriodicSource,
    cartesian_coordinates,
    render,
    spiral_coefficients,
)
from revert_escher import (
    InverseModel,
    SpiralRaster,
    reconstruction_coordinates,
    render_inverse,
)


def metadata(size=128):
    forward, inverse = spiral_coefficients(4, 1)
    return {
        'input': 'intentionally_missing_original.png',
        'input_size': [size, size],
        'final_size': [size, size],
        'fixed_point_pixel_edges': [size*0.58, size*0.44],
        'source_outer_inner_ratio': 4,
        'log_reference_radius': size,
        'turns': 1,
        'forward_log_multiplier': [forward.real, forward.imag],
        'inverse_log_multiplier': [inverse.real, inverse.imag],
        'phase_periods': 0.13,
        'source_rotation_degrees': -7,
        'view_rotation_degrees': -10.8,
        'view_scale': 0.5,
        'view_offset_canvas_fractions': [0, 0.06],
    }


class InverseEscherTests(unittest.TestCase):
    def setUp(self):
        self.parameters = metadata()
        self.model = InverseModel(self.parameters)
        yy, xx = np.mgrid[:128, :128]
        pixels = np.stack((xx, yy, (xx+yy)//2), axis=-1).astype(np.uint8)
        self.image = Image.fromarray(pixels)

    def test_coordinate_inverse_includes_upright_view_and_source_phase(self):
        u = np.array([-5.3, -2.1, -0.3])
        theta = np.array([-2.2, 0.4, 2.8])
        real, imaginary = self.model.source_to_spiral_log(u, theta)
        recovered = ((real+1j*imaginary+self.model.view_offset)/self.model.forward
                     + self.model.source_phase)
        np.testing.assert_allclose(recovered, u+1j*theta, atol=1e-12)

    def test_spiral_period_samples_same_pixels(self):
        sampler = SpiralRaster(self.image, self.model)
        u = np.array([-6.2, -3.1, -0.2])
        theta = np.array([-2.0, 0.7, 2.1])
        first, valid = sampler.sample_log(u, theta)
        second, valid2 = sampler.sample_log(u+self.model.period.real,
                                            theta+self.model.period.imag)
        self.assertTrue(valid.all() and valid2.all())
        np.testing.assert_allclose(first, second, atol=1e-8)

    def test_nonperiodic_warp_reports_missing_pixels(self):
        sampler = SpiralRaster(self.image, self.model, repeat=False)
        pixels, valid = sampler.sample_log(np.array([20.0]), np.array([0.1]))
        self.assertFalse(valid.any())
        np.testing.assert_array_equal(pixels, np.full((1, 3), 224))

    def test_reconstruction_does_not_read_original_path(self):
        sampler = SpiralRaster(self.image, self.model)
        recovered, coverage = render_inverse(
            sampler, (32, 32), reconstruction_coordinates(self.model, 32, 32),
            self.model.source_to_spiral_log, samples=1,
        )
        self.assertEqual(recovered.size, (32, 32))
        self.assertEqual(coverage.getextrema(), (255, 255))

    def test_resized_spiral_registration(self):
        small = SpiralRaster(self.image, self.model)
        # Constant image removes resampling differences: registration and coverage
        # must still work when a spiral is resized after it was generated.
        constant = Image.new('RGB', (256, 256), (42, 85, 127))
        enlarged = SpiralRaster(constant, self.model)
        self.assertEqual(enlarged.sx, 2)
        colors, valid = enlarged.sample_log(np.array([-1.0]), np.array([1.3]))
        self.assertTrue(valid.all())
        np.testing.assert_allclose(colors, [[42, 85, 127]], atol=1e-8)
        self.assertEqual(small.model.final_center, enlarged.model.final_center)

    def test_round_trip_of_smooth_periodic_image(self):
        size = 256
        parameters = metadata(size)
        model = InverseModel(parameters)
        yy, xx = np.mgrid[:size, :size]
        dx, dy = xx+0.5-model.source_center[0], model.source_center[1]-yy-0.5
        radius = np.maximum(np.hypot(dx, dy), 1e-12)
        u, theta = np.log(radius/size), np.arctan2(dy, dx)
        phase = 2*math.pi*u/math.log(4)
        pixels = np.stack((128+50*np.sin(phase), 128+40*np.cos(theta),
                           128+30*np.sin(theta+phase)), axis=-1)
        original = Image.fromarray(np.rint(pixels).astype(np.uint8))
        forward_source = PeriodicSource(original, model.source_center, 4)
        final = render(
            forward_source, size,
            cartesian_coordinates(size, (model.final_center[0]/size, model.final_center[1]/size)),
            inverse=1/model.forward, phase=parameters['phase_periods'],
            rotation=math.radians(parameters['source_rotation_degrees']),
            log_offset=model.view_offset, samples=2,
        )
        recovered, _ = render_inverse(
            SpiralRaster(final, model), (size, size), reconstruction_coordinates(model, size, size),
            model.source_to_spiral_log, samples=2,
        )
        error = np.abs(np.asarray(recovered, dtype=np.float64)-np.asarray(original, dtype=np.float64))
        self.assertLess(float(error[radius > 16].mean()), 3.0)

    def test_metadata_validation(self):
        for key, value in (('view_scale', 0), ('input_size', [128]),
                           ('fixed_point_pixel_edges', [float('nan'), 30]),
                           ('output_fixed_point_pixels', [-2, 40])):
            invalid = metadata()
            invalid[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                InverseModel(invalid)


if __name__ == '__main__':
    unittest.main()
