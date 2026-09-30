import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import build


ROOT = Path(__file__).resolve().parents[1]


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.docs_dir = self.root / "site" / "docs"
        self.docs_dir.mkdir(parents=True)

    def test_undiscoverable_entries_are_warned_and_skipped(self):
        for name, htmls in (("empty", ()), ("ambiguous", ("first.html", "second.htm"))):
            with self.subTest(name=name):
                docs_dir = self.root / name
                invalid = docs_dir / name
                invalid.mkdir(parents=True)
                for entry in htmls:
                    (invalid / entry).write_text("<p>Ambiguous</p>")
                valid = docs_dir / "valid"
                valid.mkdir()
                (valid / "index.html").write_text("<p>Valid</p>")

                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    docs = build.load_docs(docs_dir, {})

                self.assertEqual([doc["slug"] for doc in docs], ["valid"])
                self.assertIn(f"[build] 跳过（无入口 HTML）: {name}", stderr.getvalue())

    def test_entry_discovery_keeps_precedence_and_single_html_support(self):
        cases = (
            ({}, ("index.html", "report.html", "other.htm"), "index.html"),
            ({}, ("report.html", "other.htm"), "report.html"),
            ({}, ("only.html",), "only.html"),
            ({"entry": ""}, ("only.htm",), "only.htm"),
            ({"entry": "custom.htm"}, ("index.html", "custom.htm"), "custom.htm"),
        )
        for index, (meta, names, expected) in enumerate(cases):
            with self.subTest(meta=meta, names=names):
                doc_dir = self.docs_dir / str(index)
                doc_dir.mkdir()
                (doc_dir / ".docmeta.json").write_text(json.dumps(meta))
                for name in names:
                    (doc_dir / name).write_text("<p>Document</p>")
                docs = build.load_docs(self.docs_dir, {})
                doc = next(doc for doc in docs if doc["slug"] == str(index))
                self.assertEqual(doc["entry"], expected)
                self.assertEqual(doc["url"], f"docs/{index}/{expected}")

    def test_explicit_missing_entry_keeps_skip_contract(self):
        doc_dir = self.docs_dir / "missing"
        doc_dir.mkdir()
        (doc_dir / ".docmeta.json").write_text('{"entry": "missing.html"}')
        (doc_dir / "index.html").write_text("<p>Fallback must not replace explicit entry</p>")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(build.load_docs(self.docs_dir, {}), [])
        self.assertIn("[build] 跳过（无入口 missing.html）: missing", stderr.getvalue())

    def test_metadata_errors_still_propagate(self):
        doc_dir = self.docs_dir / "invalid"
        doc_dir.mkdir()
        (doc_dir / ".docmeta.json").write_text("{")
        with self.assertRaises(json.JSONDecodeError):
            build.load_docs(self.docs_dir, {})

    def test_cli_builds_samples_with_undiscoverable_entries(self):
        shutil.copy2(ROOT / "build.py", self.root / "build.py")
        for name in ("templates", "static"):
            shutil.copytree(ROOT / name, self.root / name)
        shutil.copytree(ROOT / "sample-docs", self.docs_dir, dirs_exist_ok=True)
        (self.docs_dir / "empty").mkdir()
        ambiguous = self.docs_dir / "ambiguous"
        ambiguous.mkdir()
        for name in ("first.html", "second.htm"):
            (ambiguous / name).write_text("<p>Ambiguous</p>")

        result = subprocess.run(
            [sys.executable, str(self.root / "build.py")],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        manifest = json.loads((self.root / "site" / "_data" / "manifest.json").read_text())
        self.assertEqual({doc["slug"] for doc in manifest}, {"welcome", "demo-report"})
        for name in ("empty", "ambiguous"):
            self.assertIn(f"[build] 跳过（无入口 HTML）: {name}", result.stderr)
        for path in ("index.html", "search.html", "tags.html", "static/app.js"):
            self.assertTrue((self.root / "site" / path).is_file(), path)


if __name__ == "__main__":
    unittest.main()
