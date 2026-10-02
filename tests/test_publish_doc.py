import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PUBLISH_SCRIPT = Path(__file__).resolve().parents[1] / "publish_doc.py"
PRIVATE_CONTENT = b"TEST_PRIVATE_CONTENT_MUST_NOT_BE_PUBLISHED"


class PublishDocTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.doc = self.root / "doc"
        self.doc.mkdir()
        self.out = self.root / "out"
        self.private = self.root / "private.txt"
        self.private.write_bytes(PRIVATE_CONTENT)
        (self.doc / "index.html").write_text("<p>Document</p>")

    def publish(self, source=None):
        return subprocess.run(
            [sys.executable, str(PUBLISH_SCRIPT), str(source or self.doc), str(self.out)],
            capture_output=True, text=True,
        )

    def assert_rejected(self, result):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        for path in self.out.rglob("*"):
            if path.is_file():
                self.assertNotIn(PRIVATE_CONTENT, path.read_bytes(), str(path))

    def test_escaping_resources_are_broken_links(self):
        sibling = self.root / "doc-other"
        sibling.mkdir()
        (sibling / "private.txt").write_bytes(PRIVATE_CONTENT)
        (self.doc / "linked.txt").symlink_to(self.private)
        for url in ("../private.txt", str(self.private), "linked.txt", "../doc-other/private.txt"):
            for markup in ('<img src="{}">', '<a href="{}">file</a>', '<style>p {{background:url("{}")}}</style>'):
                with self.subTest(url=url, markup=markup):
                    (self.doc / "index.html").write_text(markup.format(url))
                    result = self.publish()
                    self.assert_rejected(result)
                    self.assertIn(f"[断链] {url}", result.stdout)
                    self.assertEqual(list((self.out / "doc" / "assets").iterdir()), [])

    def test_absolute_in_root_resource_is_rejected(self):
        asset = self.doc / "image.png"
        asset.write_bytes(b"image")
        (self.doc / "index.html").write_text(f'<img src="{asset}">')
        self.assert_rejected(self.publish())

    def test_nested_html_keeps_original_document_boundary(self):
        child = self.doc / "child"
        child.mkdir()
        (child / "report.html").write_text('<img src="../../private.txt">')
        (self.doc / "index.html").write_text('<a href="child/report.html">report</a>')
        result = self.publish()
        self.assert_rejected(result)
        self.assertIn("[断链] ../../private.txt", result.stdout)

    def test_in_root_resources_and_external_urls_still_publish(self):
        (self.doc / "image.png").write_bytes(b"image")
        (self.doc / "alias.png").symlink_to(self.doc / "image.png")
        child = self.doc / "child"
        child.mkdir()
        (child / "report.html").write_text('<img src="../image.png">')
        (self.doc / "index.html").write_text(
            '<img src="alias.png?size=1#preview">'
            '<a href="child/report.html">report</a>'
            '<a href="https://example.com/a">external</a><a href="#section">anchor</a>'
        )
        (self.doc / ".docmeta.yaml").write_text("title: Document\n")
        (self.doc / "summary.md").write_text("# Summary\n")
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = self.out / "doc"
        html = (output / "index.html").read_text()
        self.assertIn("?size=1#preview", html)
        self.assertIn('href="https://example.com/a"', html)
        self.assertIn('href="#section"', html)
        files = list((output / "assets").iterdir())
        self.assertEqual(len(files), 2)
        self.assertEqual(next(p for p in files if p.suffix == ".png").read_bytes(), b"image")
        self.assertNotIn('src="../image.png"', next(p for p in files if p.suffix == ".html").read_text())
        self.assertEqual((output / "summary.md").read_text(), "# Summary\n")
        self.assertEqual((output / ".docmeta.yaml").read_text(), "title: Document\n")

    def test_configured_entries_cannot_escape_or_be_absolute(self):
        (self.doc / "linked.html").symlink_to(self.private)
        entries = ("../private.txt", str(self.private), "linked.html", str(self.doc / "index.html"), "../missing.html")
        for entry in entries:
            with self.subTest(entry=entry):
                (self.doc / ".docmeta.yaml").write_text(f"entry: {entry}\n")
                self.assert_rejected(self.publish())
                self.assertFalse(self.out.exists())

    def test_fallback_entries_cannot_follow_external_symlinks(self):
        (self.doc / "index.html").unlink()
        for name in ("index.html", "report.html"):
            with self.subTest(name=name):
                entry = self.doc / name
                entry.symlink_to(self.private)
                self.assert_rejected(self.publish())
                self.assertFalse(self.out.exists())
                entry.unlink()

    def test_metadata_cannot_follow_external_symlinks(self):
        for name in (".docmeta.yaml", "summary.md"):
            for source in (self.doc, self.doc / "index.html"):
                with self.subTest(name=name, source=source):
                    meta = self.doc / name
                    meta.symlink_to(self.private)
                    try:
                        self.assert_rejected(self.publish(source))
                    finally:
                        meta.unlink()

    def test_single_html_input_still_publishes_local_resources(self):
        (self.doc / "image.png").write_bytes(b"image")
        (self.doc / "index.html").write_text('<img src="image.png">')
        result = self.publish(self.doc / "index.html")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.out / "index" / "index.html").exists())
        self.assertEqual(len(list((self.out / "index" / "assets").iterdir())), 1)

    def test_missing_local_resource_keeps_broken_link_contract(self):
        (self.doc / "index.html").write_text('<img src="missing.png">')
        result = self.publish()
        self.assert_rejected(result)
        self.assertIn("[断链] missing.png", result.stdout)
        self.assertIn('src="missing.png"', (self.out / "doc" / "index.html").read_text())

    def test_missing_configured_entry_keeps_fallback(self):
        (self.doc / ".docmeta.yaml").write_text("entry: missing.html\n")
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.out / "doc" / "index.html").exists())

    def test_missing_entry_keeps_error_contract(self):
        (self.doc / "index.html").unlink()
        result = self.publish()
        self.assert_rejected(result)
        self.assertIn("[publish_doc] 找不到入口 HTML（index.html/report.html）:", result.stderr)


if __name__ == "__main__":
    unittest.main()
