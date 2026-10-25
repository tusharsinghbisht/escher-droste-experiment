# Stock-photo source

- Photographer: **James Wheeler**.
- Original photo page: [Pexels](https://www.pexels.com/photo/lake-and-mountain-417074/).
- Downloaded file page: [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Pexels-james-wheeler-417074.jpg).
- Direct download: [Original JPEG](https://upload.wikimedia.org/wikipedia/commons/6/60/Pexels-james-wheeler-417074.jpg).
- Local original: `source_original.jpg` (4226 x 2847 pixels).
- Experiment input: `input_4096.png` (4096 x 4096 pixels).

The input was EXIF-orientation corrected, converted to RGB, center-cropped to
a square, and resized with Lanczos. It contains **no inserted recursive copies**.
Consult the linked source pages for the photograph's usage terms.

The existing renderer was run unchanged except for its generic input caption:

```powershell
.venv\Scripts\python.exe create_escher.py --input stock_experiment/input_4096.png --output-dir stock_experiment --center 2048 2048 --ratio 4 --turns 1
```

`--ratio 4` specifies the sampler's assumed log-radius period; it does not
mean that this ordinary stock image already has a quarter-scale nested copy.
Visible repeated seams are expected because the source boundaries do not match.
