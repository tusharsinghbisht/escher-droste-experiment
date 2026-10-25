# Reversing a spiral image

## Reconstruct the generated nested image

```powershell
.venv\Scripts\python.exe revert_escher.py
```

Defaults:

- Input raster: `escher_output/03_escher.png`.
- Metadata: `escher_output/parameters.json`.
- Output: `reverted_output/03_reverted.png`, at 4096 x 4096 pixels.

The inverse includes the final upright-view rotation, zoom, translation,
source phase, and source rotation. It reconstructs the **nested image before
the spiral transform**, not the earlier empty-frame photograph.

**The original image is not read or used to reconstruct pixels.** The saved
metadata's `input` filename is deliberately ignored. An optional reference is
read only after reconstruction, for comparison:

```powershell
.venv\Scripts\python.exe revert_escher.py --reference demo2_nested_quarter.png
```

That adds `reference_comparison.jpg` and measured preview-scale RGB error/PSNR
to `inverse_report.json`. It does not fill missing pixels from the reference.

## Output stages

- `01_spiral_log.png`: log-polar view sampled from the supplied spiral raster.
- `02_unrotated_log.png`: inverse-rectified log plane.
- `03_reverted.png`: reconstructed pre-spiral image.
- `04_inverse_grid.png`: labeled 2x2 grid of input, log, corrected log, and result.
- `coverage.png`: raster sample coverage; white means samples were available.
- `preview.jpg`, `stages.jpg`: smaller previews.
- `inverse_report.json`: dimensions, coverage, limitations, and optional error.

Coverage is **not** a truth/confidence score. White pixels in the original
artwork's blank center still count as available raster pixels; that does not
mean they contain the missing drawing.

## Inverse mathematics

Let `F` be the periodically extended pre-spiral image, `J` the supplied spiral,
`a` the inverse log multiplier, and `c=1/a` the forward multiplier. Define:

```text
q = phase*ln(ratio) + i*source_rotation
m = final view scale
beta = final view rotation
d = -ln(m) - i*beta
```

The forward renderer evaluates:

```text
J(exp(w)) = F(exp(a*(w+d)+q))
```

Therefore, to recover a source coordinate `v=log(z_source)`, sample the raster at:

```text
w_spiral = c*(v-q)-d
z_spiral = exp(w_spiral)
```

The saved output fixed point locates that complex coordinate in the spiral
raster. Its dimensions register the coordinate system even when a raster has
been resized since it was generated.

Only a finite portion of the spiral is available. In periodic mode, equivalent
spiral coordinates differ by `k*c*ln(ratio)`. The sampler searches these repeats
and uses the largest-radius in-frame representative for better raster detail.
It samples **only the provided spiral**, not the original source.

For a literal inverse with no repetition outside the observed frame:

```powershell
.venv\Scripts\python.exe revert_escher.py --no-repeat --output-dir reverted_literal
```

Off-image areas then become gray and have zero coverage. This is useful when a
source is not actually self-repeating. Repeated sampling cannot recover source
content that was discarded when the forward renderer imposed a radial period
on an ordinary, nonrecursive stock photo.

Raster interpolation is lossy. The image can look very close to the original,
but exact pixel-for-pixel recovery is not generally possible, especially near
the logarithmic singularity or deeply minified copies.

## Experiment on Escher's original Print Gallery

```powershell
.venv\Scripts\python.exe run_print_gallery.py
```

This downloads the museum's original scan if it is not already cached. It
uses an HTTPS-only connection to a fixed museum asset, rejects redirects, and
limits the download to 32 MiB. To supply a local scan instead:

```powershell
.venv\Scripts\python.exe run_print_gallery.py --input path/to/print-gallery.png
```

Local results are saved under `print_gallery_experiment/inverse/`, with the
same stage names as the generated-image inverse. The original scan is 1200 x
1181; default output is 2048 square. Upsampling does not create new detail.
The download and all derived artwork are **gitignored**, not added to the
public repository automatically. The artwork is copyrighted; a publicly
viewable museum image is not a redistribution license.

### What this test does and does not establish

- It uses the published **256:1 straight-image scale period**, not our 4:1 model.
- The normalized complex-power model uses an approximate scan-center origin.
- Visitor landmarks guided a manual orientation of about -12.084 degrees;
  `--phase 0.4` and `--source-origin 0.5 0.35` select the displayed framing.
- The result is an **approximate unwarping**, not the researchers' full
  correction of Escher's hand-drawn grid.
- Blank regions and the artist's center inscription remain visible/deformed.
  The missing center is **not recovered or generated**.
- Model-based periodic extension reuses observed scan pixels. It must not be
  mistaken for historically authentic reconstructed artwork.

A literal, non-extended comparison is also available:

```powershell
.venv\Scripts\python.exe run_print_gallery.py --literal
```

This saves to `print_gallery_experiment/inverse_literal/` and explicitly marks
areas outside the observed scan gray. Try `--center X Y`, `--phase`,
`--orientation-deg`, and `--source-origin X Y` to explore scan calibration.
Settings and limitations are recorded in each output's `inverse_report.json`.

Sources:

- [Original work and museum image](https://escherinhetpaleis.nl/en/about-escher/masterpieces/print-gallery)
- [de Smit and Lenstra, Artful Mathematics](https://pub.math.leidenuniv.nl/~smitbde/papers/2003-de_smit-lenstra-escher.pdf)
- [Leiden University Escher and Droste project](https://pub.math.leidenuniv.nl/~smitbde/escherdroste/)

## Test

```powershell
.venv\Scripts\python.exe -m unittest -v
```

Tests include algebraic coordinate inversion, nonzero source/view phases,
repeat-branch consistency, raster-only reconstruction without the original,
resize registration, missing-pixel coverage, a smooth periodic round trip,
metadata validation, and safe download behavior.
