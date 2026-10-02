import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import publish_doc


PUBLISH_SCRIPT = Path(__file__).resolve().parents[1] / "publish_doc.py"


class PublishDocCycleTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.doc = self.root / "doc"
        self.doc.mkdir()
        self.out = self.root / "out"

    def publish(self, single_html=False):
        source = self.doc / "index.html" if single_html else self.doc
        return subprocess.run(
            [sys.executable, str(PUBLISH_SCRIPT), str(source), str(self.out)],
            capture_output=True, text=True, timeout=10,
        )

    def test_html_cycles_finish_and_write_each_referenced_file(self):
        cases = (
            {"index.html": "./index.html"},
            {"index.html": "a.html", "a.html": "index.html"},
            {"index.html": "a.html", "a.html": "./a.html"},
            {"index.html": "a.html", "a.html": "b.htm", "b.htm": "a.html"},
            {"index.html": "a.html", "a.html": "b.htm", "b.htm": "c.html", "c.html": "a.html"},
        )
        for links in cases:
            for single_html in (False, True):
                with self.subTest(links=links, single_html=single_html):
                    for name, target in links.items():
                        (self.doc / name).write_text(f'<a href="{target}?view=1#top">next</a>')
                    result = self.publish(single_html)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr[-600:])
                    output = self.out / ("index" if single_html else "doc")
                    referenced = {Path(target).name for target in links.values()}
                    expected = {publish_doc.flatten(self.doc / name) for name in referenced}
                    self.assertEqual({p.name for p in (output / "assets").iterdir()}, expected)
                    self.assertIn(f"资源={len(expected)} 断链=0", result.stdout)
                    for name, target in links.items():
                        flat = publish_doc.flatten(self.doc / name)
                        pages = [output / "assets" / flat] if name in referenced else []
                        if name == "index.html":
                            pages.append(output / name)
                        for page in pages:
                            target_flat = publish_doc.flatten(self.doc / target)
                            prefix = "" if page.parent == output / "assets" else "assets/"
                            self.assertEqual(page.read_text(), f'<a href="{prefix}{target_flat}?view=1#top">next</a>')

    def test_missing_link_in_cycle_keeps_failure_contract(self):
        (self.doc / "index.html").write_text('<a href="a.html">next</a>')
        (self.doc / "a.html").write_text('<a href="index.html">back</a><img src="missing.png">')
        result = self.publish()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr[-600:])
        self.assertIn("资源=2 断链=1", result.stdout)
        self.assertIn("[断链] missing.png", result.stdout)
        child = next((self.out / "doc" / "assets").glob("*_a.html"))
        self.assertIn('src="missing.png"', child.read_text())
        self.assertEqual(result.stderr, "")

    def test_repeated_acyclic_resources_keep_outputs(self):
        (self.doc / "index.html").write_text(
            '<a href="a.html?view=1#top">next</a><a href="./a.html">again</a>'
            '<a href="https://example.com/">external</a><a href="#top">anchor</a>'
        )
        (self.doc / "a.html").write_text('<img src="image.png"><img src="./image.png">')
        (self.doc / "image.png").write_bytes(b"image")
        (self.doc / ".docmeta.yaml").write_text("title: Document\n")
        (self.doc / "summary.md").write_text("# Summary\n")
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("资源=2 断链=0", result.stdout)
        output = self.out / "doc"
        html = (output / "index.html").read_text()
        self.assertIn('?view=1#top"', html)
        self.assertIn('href="https://example.com/"', html)
        self.assertIn('href="#top"', html)
        self.assertEqual((output / "summary.md").read_text(), "# Summary\n")
        self.assertEqual((output / ".docmeta.yaml").read_text(), "title: Document\n")
        files = list((output / "assets").iterdir())
        self.assertEqual(len(files), 2)
        self.assertEqual(next(p for p in files if p.suffix == ".png").read_bytes(), b"image")

    def test_copy_error_propagates(self):
        (self.doc / "index.html").write_text('<img src="image.png">')
        (self.doc / "image.png").write_bytes(b"image")
        with patch.object(sys, "argv", [str(PUBLISH_SCRIPT), str(self.doc), str(self.out)]), \
                patch.object(publish_doc.shutil, "copy2", side_effect=OSError("copy failed")):
            with self.assertRaisesRegex(OSError, "copy failed"):
                publish_doc.main()


if __name__ == "__main__":
    unittest.main()
