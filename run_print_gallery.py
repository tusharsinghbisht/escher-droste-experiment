"""Local-only inverse experiment on M.C. Escher's original Print Gallery.

Uses the published 256:1 straight-image period, with approximate scan-center
and manually chosen framing/orientation. This is NOT the full de Smit-Lenstra
hand-drawn-grid correction or their completed-center reconstruction.
Downloaded artwork and derivatives stay in the gitignored experiment folder.
"""

import argparse
import json
import math
from http.client import HTTPException, HTTPSConnection
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image

from create_escher import save_contact_sheet, spiral_coefficients
from revert_escher import run_inverse

DIRECTORY = Path(__file__).resolve().parent
IMAGE_URL = ('https://prdzoomst01.blob.core.windows.net/'
             'escher-production-silverstripe-assets-public/Uploads/Masterpiece/'
             '410-prentententoonstelling.webp')
MUSEUM_URL = 'https://escherinhetpaleis.nl/en/about-escher/masterpieces/print-gallery'
PAPER_URL = 'https://pub.math.leidenuniv.nl/~smitbde/papers/2003-de_smit-lenstra-escher.pdf'


def download_museum_image(destination):
    """Fetch the fixed museum asset over HTTPS only, without following redirects."""
    url = urlsplit(IMAGE_URL)
    if url.scheme != 'https' or not url.hostname:
        raise ValueError('The museum asset must use HTTPS.')
    connection = HTTPSConnection(url.hostname, timeout=60)
    try:
        connection.request('GET', url.path, headers={
            'User-Agent': 'EscherImageExperiment/1.0 (local mathematical image analysis)'})
        response = connection.getresponse()
        if response.status != 200:
            raise OSError(f'Museum download returned HTTP {response.status}; redirects are not followed.')
        payload = response.read(32*1024*1024+1)
        if len(payload) > 32*1024*1024:
            raise OSError('Museum image exceeds the 32 MiB download limit.')
        destination.write_bytes(payload)
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, help='Optional local original scan; otherwise use the museum image.')
    parser.add_argument('--folder', type=Path, default=DIRECTORY/'print_gallery_experiment')
    parser.add_argument('--size', type=int, default=2048)
    parser.add_argument('--samples', type=int, choices=(1, 2, 4), default=2)
    parser.add_argument('--center', type=float, nargs=2, help='Spiral center in original scan pixels; default is scan center.')
    parser.add_argument('--phase', type=float, default=0.4, help='Framing phase in ln(256) periods.')
    parser.add_argument('--orientation-deg', type=float, default=-12.0841675843489,
                        help='Approximate straight-view orientation from visitor landmarks.')
    parser.add_argument('--source-origin', type=float, nargs=2, default=(0.5, 0.35),
                        help='Untwisted view origin as canvas fractions.')
    parser.add_argument('--literal', action='store_true', help='No periodic extension: show out-of-scan regions as gray.')
    args = parser.parse_args()
    if args.size < 1 or not all(math.isfinite(value) for value in
                              (args.phase, args.orientation_deg, *args.source_origin)):
        parser.error('Size must be positive and calibration values finite.')
    try:
        args.folder.mkdir(parents=True, exist_ok=True)
        image_path = args.input or args.folder/'original_print_gallery.webp'
        if args.input is None and not image_path.exists():
            download_museum_image(image_path)
        with Image.open(image_path) as opened:
            image = opened.convert('RGB')
        width, height = image.size
        center = args.center or (width/2, height/2)
        forward, inverse = spiral_coefficients(256, 1)
        parameters = {
            'input_size': [args.size, args.size],
            'final_size': [width, height],
            'fixed_point_pixel_edges': [value*args.size for value in args.source_origin],
            'output_fixed_point_pixels': list(center),
            'source_outer_inner_ratio': 256,
            'log_reference_radius': args.size,
            'turns': 1,
            'forward_log_multiplier': [forward.real, forward.imag],
            'inverse_log_multiplier': [inverse.real, inverse.imag],
            'phase_periods': args.phase,
            'source_rotation_degrees': args.orientation_deg,
            'view_scale': 1,
            'view_rotation_degrees': 0,
            'calibration': ('Approximate complex-power model: published scale period 256; '
                            'scan-center origin and manually framed visitor landmark alignment. '
                            'Not the full hand-grid correction or missing-center reconstruction.'),
        }
        parameter_path = args.folder/'approximate_parameters.json'
        parameter_path.write_text(json.dumps(parameters, indent=2)+'\n', encoding='utf-8')
        output = args.folder/('inverse_literal' if args.literal else 'inverse')
        recovered, report = run_inverse(image_path, parameters, output, args.size,
                                        args.size, args.samples, not args.literal)
        with Image.open(output/'01_spiral_log.png') as first, Image.open(output/'02_unrotated_log.png') as second:
            stages = [('Original Print Gallery (1956)', image), ('1. Spiral log plane', first),
                      ('2. Approx. unrotated log', second), ('3. Approx. straightened view', recovered)]
            save_contact_sheet(stages, output/'04_inverse_grid.png', tile_size=2048)
            save_contact_sheet(stages, output/'stages.jpg')
        report['experiment'] = 'Approximate unwarping of original Print Gallery, not exact recovery.'
        report['calibration'] = parameters['calibration']
        report['artwork_source'] = MUSEUM_URL
        report['mathematical_source'] = PAPER_URL
        report['blank_center_recovered'] = False
        (output/'inverse_report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        notes = (
            '# Original Print Gallery: local inverse experiment\n\n'
            'M.C. Escher, Print Gallery (Prentententoonstelling), lithograph, May 1956.\n\n'
            f'- [Museum artwork page]({MUSEUM_URL})\n'
            f'- [Downloaded museum image]({IMAGE_URL})\n'
            f'- [de Smit and Lenstra: Artful Mathematics]({PAPER_URL})\n\n'
            'The artwork is copyrighted. These local analysis files and derivatives\n'
            'are excluded from Git; access to a museum image is not a redistribution license.\n\n'
            'This experiment applies an approximate complex-power model with scale period 256.\n'
            'It does not implement the researchers\' full correction of Escher\'s hand-drawn grid.\n'
            'The original blank center and finite scan impose unrecoverable missing information.\n'
            'Periodic mode reuses observed scan content at equivalent model repeats; it does not\n'
            'create historically authentic missing artwork. Literal mode leaves off-scan areas gray.\n'
        )
        (args.folder/'SOURCE.md').write_text(notes, encoding='utf-8')
    except (OSError, ValueError, KeyError, TypeError, OverflowError, HTTPException) as error:
        parser.exit(2, f'Print Gallery experiment failed: {error}\n')


if __name__ == '__main__':
    main()
