# Complex-plane spiral Droste image

`create_escher.py` transforms `demo2_nested_quarter.png` through complex log,
a rotation plus scale correction in the log plane, and the complex exponential.
It leaves the source image unchanged and saves all stages in `escher_output/`.

## Run

The local `.venv` already has the dependencies installed:

```powershell
.venv\Scripts\python.exe create_escher.py
```

To set up again:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe create_escher.py
```

Or use `py -3.11 create_escher.py` if Pillow and NumPy are installed there.
Recreate the source image first with `create_nested.py` if needed.

## Saved images

- `01_log_polar.png`: unwrapped source in the complex-log plane.
- `02_rotated_log.png`: rotated and slightly scaled log plane.
- `03_escher.png`: exponential back to Cartesian space; the final spiral image.
- `04_transformation_grid.png`: labeled **2x2 grid**, source / log / rotated log /
  final, in reading order. Each image tile is 2048 square; including captions,
  the whole grid is 4096 x 4224 pixels.
- `preview.jpg`: 1024-square preview of the final image.
- `stages.jpg`: smaller preview of the 2x2 grid.
- `parameters.json`: exact center, coefficients, phases, dimensions, and angles.

All three individual transformation stages default to 4096 x 4096 pixels.
The intermediate log window has real coordinate `[-2*pi, 0]` horizontally,
and imaginary coordinate `[pi, -pi]` from top to bottom. Both axes use equal
units. This shows radii from approximately 7.65 to 4096 source pixels.

## Mathematics

Coordinates are measured at pixel edges (a pixel center is `x+0.5, y+0.5`).
The source recursion is `z -> t + s*z`, where `s=1/4` and `t=(2287, 537)`
in raster coordinates. Its fixed point is

```text
p = t / (1-s) = (3049.333333333333, 716)
```

This is the point to put at the complex origin, **not** the picture-frame center.
Imaginary coordinates point up; raster y points down. With reference radius
`R=4096`, normalize to `z=((x-px) + i*(py-y))/R` and take `w=log(z)`.

The recursive source has a log-radius period `L=ln(4)` and an angular period
`2*pi`. An arbitrary pure rotation of its log plane generally leaves a branch
seam when the angle wraps. For integer winding `n`, instead use

```text
a = 1 - i*n*L/(2*pi)          # inverse multiplier
c = 1/a                     # forward rotation AND uniform scale
z_out = exp(c * log(z_in))
```

Because `c*(n*L + 2*pi*i) = 2*pi*i`, one output revolution corresponds to a
whole number of source repeats plus one source revolution. This closes the
angular seam mathematically. For the default `n=1`, the log-plane rotation is
about 12.44 degrees, with a small uniform scale correction. The final spiral's
repeat scale and rotation differ from the original 4:1 source; their exact
values are recorded in `parameters.json`.

Image resampling is **inverse mapped**. If `F` is the extended source, the
saved rotated log image evaluates `F(exp(a*w))`, and the final image evaluates
`F(exp(a*log(z_out)))`. This is the same continuous log/rotate/exp pipeline,
without rereading a cropped intermediate bitmap or adding extra raster blur.

The source is extended infinitely by folding each log-radius into the region
between the outer image rectangle and its quarter-size inner copy. That makes
the recursive period exact even though the supplied image has only finitely
many visible levels. Bilinear sampling and 2x2 subpixel sampling reduce aliasing;
very fine structure at the logarithmic center remains resolution-limited.
No finite-resolution raster can preserve infinitely many levels.

## Upright final view

The image currently saved in `escher_output/` was reframed to make the main
woman upright. Reproduce it with:

```powershell
.venv\Scripts\python.exe create_escher.py --view-rotation-deg -10.823111593168614 --view-scale 0.5 --view-offset 0 0.06
```

This applies a rigid final-view rotation of 10.823 degrees clockwise, a scale
of 0.5, and a downward translation of 6% of the canvas. It aligns a reference
head-to-hip axis; it does not straighten all curved details of the spiral.
The progressively smaller women are intentionally rotated relative to each
other. The source photograph and the stock-photo experiment are unchanged.

If `beta` is the view angle and `m` the view scale, the forward view is
`z_view = m*exp(i*beta)*z_spiral`. In inverse mapping, subtract
`ln(m) + i*beta` from the output log coordinate before multiplying by `a`.
Both the rotated-log stage and final stage use this same offset. Translation
moves the output fixed point but does not alter the source recursion center.
All view settings are recorded in `parameters.json`.

These settings are explicit CLI options, not defaults for arbitrary inputs.
Running without them uses the original view. The old final is backed up as
`03_escher_before_upright.png`.

## Variations

```powershell
# Reverse the spiral; use another directory to retain the first result.
.venv\Scripts\python.exe create_escher.py --turns -1 --output-dir escher_reverse

# Stronger winding.
.venv\Scripts\python.exe create_escher.py --turns 2 --output-dir escher_stronger

# Quick low-resolution experiment (the grid still has 2048px tiles).
.venv\Scripts\python.exe create_escher.py --size 1024 --log-size 1024 --samples 1 --output-dir escher_test

# Shift the repeated source radially and angularly.
.venv\Scripts\python.exe create_escher.py --phase 0.25 --rotation-deg 20

# Test mathematical periodicity, angular closure, sampling, and grid layout.
.venv\Scripts\python.exe -m unittest -v
```

`--turns 0` disables the spiral. `--samples 4` uses 16 samples per pixel for
higher-quality but slower rendering. For a different source, supply its true
outer/inner `--ratio` and recursion fixed point with `--center X Y`; the default
geometry is specific to this project's quarter-frame image. A random image
without a matching recursive seam will not become seamless merely by supplying
a ratio and center.
