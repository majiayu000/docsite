import builtins
import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build


class DocumentMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name).resolve()
        self.docs_dir = self.root / "site" / "docs"
        self.docs_dir.mkdir(parents=True)

    def make_doc(self, name, filename=None, content=None):
        doc = self.docs_dir / name
        if doc.exists():
            shutil.rmtree(doc)
        doc.mkdir()
        (doc / "index.html").write_text("<title>Document</title>", encoding="utf-8")
        if filename:
            (doc / filename).write_text(content, encoding="utf-8")
        return doc

    def test_parser_errors_skip_only_the_bad_document(self):
        for filename, content, error_name in (
            (".docmeta.json", "{", "JSONDecodeError"),
            (".docmeta.yaml", "tags: [unfinished", "ParserError"),
        ):
            with self.subTest(filename=filename):
                invalid = self.make_doc("a-bad", filename, content)
                valid = self.make_doc("z-valid", ".docmeta.json", '{"tags": ["kept"]}')
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    docs = build.load_docs(self.docs_dir, {})
                self.assertEqual([doc["slug"] for doc in docs], ["z-valid"])
                self.assertEqual(docs[0]["tags"], ["kept"])
                self.assertIn(str(invalid), stderr.getvalue())
                self.assertIn(error_name, stderr.getvalue())
                shutil.rmtree(invalid)
                shutil.rmtree(valid)

    def test_non_mapping_metadata_is_skipped(self):
        for filename, contents in (
            (".docmeta.json", ("[]", "null", "false", "1", '"text"')),
            (".docmeta.yaml", ("[]", "false", "1", "text")),
        ):
            for content in contents:
                with self.subTest(filename=filename, content=content):
                    invalid = self.make_doc("a-bad", filename, content)
                    valid = self.make_doc("z-valid")
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        docs = build.load_docs(self.docs_dir, {})
                    self.assertEqual([doc["slug"] for doc in docs], ["z-valid"])
                    self.assertIn(str(invalid), stderr.getvalue())
                    self.assertIn("TypeError", stderr.getvalue())
                    shutil.rmtree(invalid)
                    shutil.rmtree(valid)

    def test_non_list_tags_are_skipped_without_character_or_key_tags(self):
        for tags in (1, None, "text", {"key": "value"}):
            for filename, content in (
                (".docmeta.json", json.dumps({"tags": tags})),
                (".docmeta.yaml", yaml.safe_dump({"tags": tags})),
            ):
                with self.subTest(filename=filename, tags=tags):
                    invalid = self.make_doc("a-bad", filename, content)
                    valid = self.make_doc("z-valid")
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        docs = build.load_docs(self.docs_dir, {})
                    self.assertEqual([doc["slug"] for doc in docs], ["z-valid"])
                    self.assertIn(str(invalid), stderr.getvalue())
                    self.assertIn("tags", stderr.getvalue())
                    self.assertIn("TypeError", stderr.getvalue())
                    shutil.rmtree(invalid)
                    shutil.rmtree(valid)

    def test_valid_metadata_and_empty_yaml_keep_existing_behavior(self):
        self.make_doc("json", ".docmeta.json", '{"title": "JSON", "tags": ["one", 2]}')
        self.make_doc("yaml", ".docmeta.yaml", "title: YAML\ntags: [two]\n")
        self.make_doc("empty", ".docmeta.yaml", "")
        self.make_doc("missing")
        self.make_doc("draft", ".docmeta.json", '{"draft": true}')
        docs = {doc["slug"]: doc for doc in build.load_docs(self.docs_dir, {})}
        self.assertEqual(set(docs), {"json", "yaml", "empty", "missing"})
        self.assertEqual(docs["json"]["title"], "JSON")
        self.assertEqual(docs["json"]["tags"], ["one", "2"])
        self.assertEqual(docs["yaml"]["tags"], ["two"])
        self.assertEqual(docs["empty"]["tags"], [])
        self.assertEqual(docs["missing"]["tags"], [])

    def test_json_precedence_does_not_fall_back_after_a_parse_error(self):
        invalid = self.make_doc("a-bad", ".docmeta.json", "{")
        (invalid / ".docmeta.yaml").write_text("title: Do not use\n", encoding="utf-8")
        self.make_doc("z-valid")
        with contextlib.redirect_stderr(io.StringIO()):
            docs = build.load_docs(self.docs_dir, {})
        self.assertEqual([doc["slug"] for doc in docs], ["z-valid"])
        with self.assertRaises(json.JSONDecodeError):
            build.parse_meta(invalid)

    def test_path_boundary_errors_after_scan_still_propagate(self):
        invalid = self.make_doc("a-changed", ".docmeta.json", "{}")
        self.make_doc("z-valid")
        outside = self.root / "private.json"
        outside.write_text('{"title": "SYNTHETIC_PRIVATE"}', encoding="utf-8")
        parse_meta = build.parse_meta

        def changed_after_scan(path):
            if path == invalid:
                metadata = path / ".docmeta.json"
                metadata.unlink()
                metadata.symlink_to(outside)
            return parse_meta(path)

        with patch.object(build, "parse_meta", side_effect=changed_after_scan):
            with self.assertRaisesRegex(ValueError, "path outside document"):
                build.load_docs(self.docs_dir, {})

    def test_invalid_utf8_is_skipped_and_reported(self):
        for filename in (".docmeta.json", ".docmeta.yaml"):
            with self.subTest(filename=filename):
                invalid = self.make_doc("a-invalid-encoding")
                (invalid / filename).write_bytes(b"\xff")
                self.make_doc("z-valid")
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    docs = build.load_docs(self.docs_dir, {})
                self.assertEqual([doc["slug"] for doc in docs], ["z-valid"])
                self.assertIn(str(invalid), stderr.getvalue())
                self.assertIn("UnicodeDecodeError", stderr.getvalue())

    def test_metadata_io_errors_still_propagate(self):
        invalid = self.make_doc("a-unreadable", ".docmeta.json", "{}")
        self.make_doc("z-valid")
        read_text = Path.read_text

        def read_with_failure(path, *args, **kwargs):
            if path == invalid / ".docmeta.json":
                raise PermissionError("metadata is unreadable")
            return read_text(path, *args, **kwargs)

        with patch.object(Path, "read_text", read_with_failure):
            with self.assertRaisesRegex(PermissionError, "metadata is unreadable"):
                build.load_docs(self.docs_dir, {})

    def test_missing_optional_yaml_dependency_keeps_warning_and_json_support(self):
        self.make_doc("json", ".docmeta.json", '{"tags": ["kept"]}')
        self.make_doc("yaml", ".docmeta.yaml", "title: Optional\n")
        import_module = builtins.__import__

        def import_without_yaml(name, *args, **kwargs):
            if name == "yaml":
                raise ImportError("pyyaml is not installed")
            return import_module(name, *args, **kwargs)

        stderr = io.StringIO()
        with patch("builtins.__import__", import_without_yaml), contextlib.redirect_stderr(stderr):
            docs = {doc["slug"]: doc for doc in build.load_docs(self.docs_dir, {})}
        self.assertEqual(set(docs), {"json", "yaml"})
        self.assertEqual(docs["json"]["tags"], ["kept"])
        self.assertEqual(docs["yaml"]["title"], "yaml")
        self.assertIn("需要 pyyaml", stderr.getvalue())

    def test_cli_builds_remaining_documents_and_reports_metadata_errors(self):
        shutil.copy2(build.ROOT / "build.py", self.root / "build.py")
        for name in ("templates", "static"):
            shutil.copytree(build.ROOT / name, self.root / name)
        shutil.copytree(build.ROOT / "sample-docs", self.docs_dir, dirs_exist_ok=True)
        for name, filename, content in (
            ("a-json", ".docmeta.json", "{"),
            ("b-array", ".docmeta.json", "[]"),
            ("c-tags", ".docmeta.json", '{"tags": 1}'),
            ("d-yaml", ".docmeta.yaml", "tags: [unfinished"),
        ):
            self.make_doc(name, filename, content)
        result = subprocess.run(
            [sys.executable, str(self.root / "build.py")],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        manifest = json.loads((self.root / "site/_data/manifest.json").read_text())
        self.assertEqual({doc["slug"] for doc in manifest}, {"welcome", "demo-report"})
        for name in ("a-json", "b-array", "c-tags", "d-yaml"):
            self.assertIn(str(self.docs_dir / name), result.stderr)
        for path in ("index.html", "search.html", "tags.html", "archive/2026-06.html",
                     "c/guide.html", "c/report.html", "static/app.js"):
            self.assertTrue((self.root / "site" / path).is_file(), path)


if __name__ == "__main__":
    unittest.main()
