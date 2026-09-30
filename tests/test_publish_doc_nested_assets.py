import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build
import publish_doc


PUBLISH_SCRIPT = Path(__file__).resolve().parents[1] / "publish_doc.py"


class PublishDocNestedAssetsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.doc = self.root / "doc"
        (self.doc / "sub" / "deeper").mkdir(parents=True)
        self.out = self.root / "out"

    def publish(self, single_html=False):
        source = self.doc / "index.html" if single_html else self.doc
        return subprocess.run(
            [sys.executable, str(PUBLISH_SCRIPT), str(source), str(self.out)],
            capture_output=True, text=True, timeout=10,
        )

    def test_nested_pages_resolve_peer_assets_and_preserve_entry_links(self):
        (self.doc / "index.html").write_text(
            '<a href="sub/child.html?view=1#top">child</a>'
            '<img src="sub/pic.png"><style>body{background:url(sub/pic.png)}</style>'
        )
        (self.doc / "sub" / "child.html").write_text(
            '<img src="pic.png?size=2#image"><video poster="pic.png"></video>'
            '<a href="deeper/grandchild.htm#section">next</a>'
            '<style>body{background:url(\'pic.png?size=3#bg\')}</style>'
            '<a href="https://example.com/page">external</a><a href="#top">anchor</a>'
        )
        (self.doc / "sub" / "deeper" / "grandchild.htm").write_text(
            '<img src="../pic.png"><script src="script.js"></script>'
        )
        (self.doc / "sub" / "pic.png").write_bytes(b"image fixture")
        (self.doc / "sub" / "deeper" / "script.js").write_text("console.log('fixture');")
        image_name = publish_doc.flatten(self.doc / "sub" / "pic.png")
        child_name = publish_doc.flatten(self.doc / "sub" / "child.html")
        grandchild_name = publish_doc.flatten(self.doc / "sub" / "deeper" / "grandchild.htm")
        for single_html in (False, True):
            with self.subTest(single_html=single_html):
                result = self.publish(single_html)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("资源=4 断链=0", result.stdout)
                output = self.out / ("index" if single_html else "doc")
                entry = output / "index.html"
                child = output / "assets" / child_name
                grandchild = output / "assets" / grandchild_name
                for page in (entry, child, grandchild):
                    self.assertEqual(build.check_broken(page.parent, page.name), [], page.read_text())
                self.assertIn(f'href="assets/{child_name}?view=1#top"', entry.read_text())
                self.assertIn(f'url("assets/{image_name}")', entry.read_text())
                self.assertIn(f'src="{image_name}?size=2#image"', child.read_text())
                self.assertIn(f'url("{image_name}?size=3#bg")', child.read_text())
                self.assertIn('href="https://example.com/page"', child.read_text())
                self.assertIn('href="#top"', child.read_text())
                self.assertEqual((output / "assets" / image_name).read_bytes(), b"image fixture")

    def test_missing_nested_resource_keeps_failure_contract(self):
        (self.doc / "index.html").write_text('<a href="sub/child.html">child</a>')
        (self.doc / "sub" / "child.html").write_text('<img src="missing.png?size=2#image">')
        result = self.publish()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("资源=1 断链=1", result.stdout)
        self.assertIn("[断链] missing.png?size=2#image", result.stdout)
        child = next((self.out / "doc" / "assets").glob("*_child.html"))
        self.assertEqual(child.read_text(), '<img src="missing.png?size=2#image">')

    def test_nested_resource_copy_error_propagates(self):
        (self.doc / "index.html").write_text('<a href="sub/child.html">child</a>')
        (self.doc / "sub" / "child.html").write_text('<img src="pic.png">')
        (self.doc / "sub" / "pic.png").write_bytes(b"image fixture")
        with patch.object(sys, "argv", [str(PUBLISH_SCRIPT), str(self.doc), str(self.out)]), \
                patch.object(publish_doc.shutil, "copy2", side_effect=OSError("copy failed")):
            with self.assertRaisesRegex(OSError, "copy failed"):
                publish_doc.main()


if __name__ == "__main__":
    unittest.main()
