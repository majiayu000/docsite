import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import publish_doc


PUBLISH_SCRIPT = Path(__file__).resolve().parents[1] / "publish_doc.py"


class PublishDocDirectoryUrlsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name).resolve()
        self.doc = self.root / "doc"
        self.doc.mkdir()
        self.out = self.root / "out"

    def publish(self, single_html=False):
        source = self.doc / "index.html" if single_html else self.doc
        return subprocess.run(
            [sys.executable, str(PUBLISH_SCRIPT), str(source), str(self.out)],
            capture_output=True, text=True, timeout=10,
        )

    def test_directory_urls_keep_paths_and_finish_bundle_with_failure_status(self):
        (self.doc / "folder").mkdir()
        (self.doc / "folder.html").mkdir()
        (self.doc / "image.png").write_bytes(b"image fixture")
        (self.doc / "summary.md").write_text("# Summary\n")
        directory_urls = ("./", "folder/", "folder.html?view=1#top", "folder/?view=2#bg")
        (self.doc / "index.html").write_text(
            '<a href="./">directory</a><img src="folder/">'
            '<a href="folder.html?view=1#top">HTML-named directory</a>'
            '<style>body{background:url(\'folder/?view=2#bg\')}</style>'
            '<img src="image.png?size=2#image"><img src="image.png">'
        )
        for single_html in (False, True):
            with self.subTest(single_html=single_html):
                result = self.publish(single_html)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertIn("资源=1 断链=4", result.stdout)
                output = self.out / ("index" if single_html else "doc")
                html = (output / "index.html").read_text()
                for url in directory_urls:
                    self.assertIn(f'"{url}"', html)
                    self.assertIn(f"[断链] {url}\n", result.stdout)
                image_name = publish_doc.flatten(self.doc / "image.png")
                self.assertIn(f'src="assets/{image_name}?size=2#image"', html)
                self.assertEqual(list((output / "assets").iterdir()), [output / "assets" / image_name])
                self.assertEqual((output / "assets" / image_name).read_bytes(), b"image fixture")
                self.assertEqual((output / "summary.md").read_text(), "# Summary\n")

    def test_nested_html_directory_url_is_reported_and_regular_resources_are_copied(self):
        sub = self.doc / "sub"
        sub.mkdir()
        (sub / "image.png").write_bytes(b"nested image fixture")
        (sub / "child.html").write_text('<a href="./?view=1#top">directory</a><img src="image.png">')
        (self.doc / "index.html").write_text('<a href="sub/child.html">child</a>')
        result = self.publish()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("资源=2 断链=1", result.stdout)
        self.assertIn("[断链] ./?view=1#top\n", result.stdout)
        assets = self.out / "doc" / "assets"
        self.assertIn('href="./?view=1#top"', (assets / publish_doc.flatten(sub / "child.html")).read_text())
        self.assertEqual((assets / publish_doc.flatten(sub / "image.png")).read_bytes(), b"nested image fixture")

    def test_missing_resource_keeps_failure_status_and_original_url(self):
        (self.doc / "index.html").write_text('<img src="missing.png?size=2#image">')
        result = self.publish()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("资源=0 断链=1", result.stdout)
        self.assertIn("[断链] missing.png?size=2#image\n", result.stdout)
        self.assertEqual((self.out / "doc" / "index.html").read_text(), '<img src="missing.png?size=2#image">')

    def test_regular_file_copy_error_propagates(self):
        (self.doc / "index.html").write_text('<img src="image.png">')
        (self.doc / "image.png").write_bytes(b"image fixture")
        with patch.object(sys, "argv", [str(PUBLISH_SCRIPT), str(self.doc), str(self.out)]), \
                patch.object(publish_doc.shutil, "copy2", side_effect=OSError("copy failed")):
            with self.assertRaisesRegex(OSError, "copy failed"):
                publish_doc.main()


if __name__ == "__main__":
    unittest.main()
