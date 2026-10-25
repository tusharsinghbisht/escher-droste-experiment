"""Mathematical and image-output checks; run: py -3.11 -m unittest -v."""

import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from create_escher import (
    TAU,
    PeriodicSource,
    cartesian_coordinates,
    log_coordinates,
    render,
    save_contact_sheet,
    spiral_coefficients,
)


class EscherTests(unittest.TestCase):
    def setUp(self):
        yy, xx = np.mgrid[:96, :96]
        self.pixels = np.stack((xx*2, yy*2, xx+yy), axis=-1).astype(np.uint8)
        self.image = Image.fromarray(self.pixels)
        self.source = PeriodicSource(self.image, (71.25, 16.75), 4)
        rng = np.random.default_rng(42)
        self.u = rng.uniform(-12, 1, 200)
        self.theta = rng.uniform(-math.pi, math.pi, 200)

    def test_forward_inverse_and_angular_closure(self):
        for turns in (-2, -1, 0, 1, 2):
            forward, inverse = spiral_coefficients(4, turns)
            self.assertAlmostEqual(abs(forward*inverse - 1), 0)
            period = turns*math.log(4) + TAU*1j
            self.assertAlmostEqual(abs(forward*period - TAU*1j), 0)

    def test_radial_periodicity(self):
        np.testing.assert_allclose(
            self.source.sample_log(self.u, self.theta),
            self.source.sample_log(self.u + math.log(4), self.theta), atol=1e-8,
        )

    def test_angular_periodicity(self):
        np.testing.assert_allclose(
            self.source.sample_log(self.u, self.theta),
            self.source.sample_log(self.u, self.theta + TAU), atol=1e-8,
        )

    def test_spiral_has_no_angular_branch_seam(self):
        for turns in (-1, 1, 2):
            _, inverse = spiral_coefficients(4, turns)
            w1 = inverse*(self.u + 1j*self.theta)
            w2 = inverse*(self.u + 1j*(self.theta + TAU))
            np.testing.assert_allclose(
                self.source.sample_log(w1.real, w1.imag),
                self.source.sample_log(w2.real, w2.imag), atol=1e-8,
            )

    def test_spiral_scale_and_rotation_repeat(self):
        forward, inverse = spiral_coefficients(4, 1)
        w1 = inverse*(self.u + 1j*self.theta)
        w2 = inverse*(self.u + 1j*self.theta + forward*math.log(4))
        np.testing.assert_allclose(
            self.source.sample_log(w1.real, w1.imag),
            self.source.sample_log(w2.real, w2.imag), atol=1e-8,
        )

    def test_outer_shell_preserves_original_pixels(self):
        yy, xx = np.mgrid[:96:7, :96:7]
        x, y = xx.ravel()+0.5, yy.ravel()+0.5
        cx, cy = self.source.cx, self.source.cy
        inner_left, inner_top = cx*0.75, cy*0.75
        keep = ~((x > inner_left) & (x < inner_left+24)
                 & (y > inner_top) & (y < inner_top+24))
        x, y, xx, yy = x[keep], y[keep], xx.ravel()[keep], yy.ravel()[keep]
        u = np.log(np.hypot(x-cx, cy-y)/96)
        theta = np.arctan2(cy-y, x-cx)
        np.testing.assert_allclose(self.source.sample_log(u, theta),
                                   self.pixels[yy, xx], atol=1e-8)

    def test_log_center_is_finite(self):
        mapper = cartesian_coordinates(9, (0.5, 0.5))
        u, theta = mapper(np.array([[4.5]]), np.array([[4.5]]))
        self.assertTrue(np.isfinite(u).all())
        self.assertTrue(np.isfinite(self.source.sample_log(u, theta)).all())

    def test_view_offset_matches_equivalent_source_phase(self):
        _, inverse = spiral_coefficients(4, 1)
        offset = complex(-math.log(0.5), -math.radians(-10.823111593168614))
        source_offset = inverse*offset
        actual = render(self.source, 24, log_coordinates(24), inverse=inverse,
                        samples=1, log_offset=offset)
        expected = render(self.source, 24, log_coordinates(24), inverse=inverse,
                          samples=1, phase=source_offset.real/self.source.period,
                          rotation=source_offset.imag)
        np.testing.assert_allclose(np.asarray(actual), np.asarray(expected), atol=1)

    def test_upright_view_aligns_main_woman_landmarks(self):
        forward, _ = spiral_coefficients(4, 1)
        center = complex(2287/0.75, -537/0.75)
        landmarks = []
        for x, y in ((355, 190), (340, 855)):
            z = (complex(x, -y)*4096/1254-center)/4096
            angle = np.angle(z)
            if angle > 0:
                angle -= TAU
            warped = 4096*np.exp(forward*complex(math.log(abs(z)), angle))
            oriented = 0.5*np.exp(1j*math.radians(-10.823111593168614))*warped
            landmarks.append(center + oriented - 1j*0.06*4096)
        head, hips = landmarks
        self.assertAlmostEqual(head.real, hips.real, places=6)
        self.assertGreater(head.imag, hips.imag)
        for point in landmarks:
            self.assertTrue(0 < point.real < 4096 and 0 < -point.imag < 4096)

    def test_two_by_two_grid_order(self):
        colors = ('red', 'green', 'blue', 'yellow')
        stages = [('', Image.new('RGB', (16, 16), color)) for color in colors]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'grid.png'
            save_contact_sheet(stages, path, tile_size=64)
            with Image.open(path) as grid:
                self.assertEqual(grid.size, (128, 200))
                for i, color in enumerate(colors):
                    point = ((i % 2)*64+32, (i // 2)*100+68)
                    self.assertEqual(grid.getpixel(point),
                                     Image.new('RGB', (1, 1), color).getpixel((0, 0)))

    def test_invalid_parameters(self):
        for ratio in (1, 0, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                spiral_coefficients(ratio, 1)
        with self.assertRaises(ValueError):
            PeriodicSource(self.image, (0, 12), 4)
        with self.assertRaises(ValueError):
            spiral_coefficients(4, 0.5)


if __name__ == '__main__':
    unittest.main()
