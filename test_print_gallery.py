"""HTTPS-only download checks; no network or copyrighted assets are needed."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from run_print_gallery import download_museum_image


class PrintGalleryDownloadTests(unittest.TestCase):
    @patch('run_print_gallery.HTTPSConnection')
    def test_https_asset_download(self, connection_class):
        connection = connection_class.return_value
        response = connection.getresponse.return_value
        response.status = 200
        response.read.return_value = b'test image payload'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'image.webp'
            download_museum_image(path)
            self.assertEqual(path.read_bytes(), b'test image payload')
        connection_class.assert_called_once_with('prdzoomst01.blob.core.windows.net', timeout=60)
        connection.request.assert_called_once()
        connection.close.assert_called_once()

    @patch('run_print_gallery.HTTPSConnection')
    def test_redirect_is_rejected_without_writing_file(self, connection_class):
        connection = connection_class.return_value
        connection.getresponse.return_value.status = 302
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'image.webp'
            with self.assertRaises(OSError):
                download_museum_image(path)
            self.assertFalse(path.exists())
        connection.close.assert_called_once()

    @patch('run_print_gallery.HTTPSConnection')
    @patch('run_print_gallery.IMAGE_URL', 'file:///tmp/not-allowed')
    def test_non_https_scheme_is_rejected(self, connection_class):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            download_museum_image(Path(directory)/'image.webp')
        connection_class.assert_not_called()


if __name__ == '__main__':
    unittest.main()
