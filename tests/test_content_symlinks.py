import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("docsite_build", ROOT / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class ContentSymlinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.docs = self.root / "docs"
        self.doc = self.docs / "report"
        self.doc.mkdir(parents=True)
        (self.doc / "index.html").write_text("<h1>Report</h1>")

    def test_summary_cannot_read_outside_document(self):
        outside = self.root / "outside.md"
        outside.write_text("# private fixture title\n")
        (self.doc / "summary.md").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "outside document"):
            build.read_summary_title(self.doc)

    def test_metadata_cannot_read_outside_document(self):
        for name, text in ((".docmeta.json", '{"title": "private fixture"}'),
                           (".docmeta.yaml", "title: private fixture\n")):
            with self.subTest(name=name):
                outside = self.root / name
                outside.write_text(text)
                link = self.doc / name
                link.symlink_to(outside)
                try:
                    with self.assertRaisesRegex(ValueError, "outside document"):
                        build.parse_meta(self.doc)
                finally:
                    link.unlink()

    def test_build_rejects_file_and_directory_symlinks(self):
        outside = self.root / "outside.txt"
        outside.write_text("private fixture")
        for name, target in (("report/asset.txt", outside),
                             (".hidden-link", self.root / "missing"),
                             ("linked-doc", self.root),
                             ("local-link", self.doc / "index.html")):
            with self.subTest(name=name):
                link = self.docs / name
                link.symlink_to(target)
                try:
                    with self.assertRaisesRegex(ValueError, "symlink"):
                        build.load_docs(self.docs, {})
                finally:
                    link.unlink()

    def test_regular_content_still_builds(self):
        (self.doc / "summary.md").write_text("# Report title\n")
        docs = build.load_docs(self.docs, {})
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["title"], "Report title")

    def test_main_rejects_unresolved_docs_root_symlink(self):
        for config, relative in (({}, "site/docs"),
                                 ({"docs_dir": "configured-docs"}, "configured-docs")):
            with self.subTest(config=config):
                link = self.root / relative
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(self.docs)
                try:
                    with mock.patch.object(build, "ROOT", self.root), \
                         mock.patch.object(build, "load_config", return_value=config):
                        with self.assertRaisesRegex(ValueError, "symlink"):
                            build.main()
                    self.assertFalse((self.root / "site" / "_data").exists())
                finally:
                    link.unlink()

    def test_hook_rejects_git_symlink_before_public_checkout(self):
        repo = self.root / "content.git"
        source = self.root / "source"
        work = self.root / "public-docs"
        app = self.root / "app"
        work.mkdir()
        app.mkdir()
        (app / "build.py").write_text(
            "from pathlib import Path\nPath('build-ran').touch()\n")
        self.git("-c", "init.defaultBranch=master", "init", "--bare", str(repo))
        self.git("init", "-b", "main", str(source))
        self.git("-C", str(source), "config", "user.name", "Docsite test")
        self.git("-C", str(source), "config", "user.email", "test@example.com")
        (source / "index.html").write_text("<h1>Safe</h1>")
        (source / "old.html").write_text("old content")
        self.git("-C", str(source), "add", ".")
        self.git("-C", str(source), "commit", "-m", "safe content")
        self.git("-C", str(source), "push", str(repo), "main")
        env = {**os.environ, "DOCSITE_REPO": str(repo),
               "DOCSITE_WORK": str(work), "DOCSITE_ROOT": str(app)}
        safe = subprocess.run(["bash", str(ROOT / "hooks/post-receive")],
                              env=env, capture_output=True, text=True)
        self.assertEqual(safe.returncode, 0, safe.stdout + safe.stderr)
        self.assertEqual(self.git("--git-dir", str(repo), "symbolic-ref", "HEAD")
                         .stdout.strip(), "refs/heads/main")
        clone = self.root / "clone"
        self.git("clone", str(repo), str(clone))
        self.assertEqual((clone / "index.html").read_text(), "<h1>Safe</h1>")
        self.assertTrue((app / "build-ran").exists())
        (app / "build-ran").unlink()
        (source / "old.html").unlink()
        self.git("-C", str(source), "add", ".")
        self.git("-C", str(source), "commit", "-m", "delete old content")
        self.git("-C", str(source), "push", str(repo), "main")
        updated = subprocess.run(["bash", str(ROOT / "hooks/post-receive")],
                                 env=env, capture_output=True, text=True)
        self.assertEqual(updated.returncode, 0, updated.stdout + updated.stderr)
        self.assertFalse((work / "old.html").exists())
        (app / "build-ran").unlink()
        safe_sha = self.git("--git-dir", str(repo), "rev-parse", "main").stdout.strip()
        outside = self.root / "outside.txt"
        outside.write_text("private fixture")
        (source / "leak.txt").symlink_to(outside)
        self.git("-C", str(source), "add", ".")
        self.git("-C", str(source), "commit", "-m", "symlink content")
        self.git("-C", str(source), "push", str(repo), "main")
        rejected = subprocess.run(["bash", str(ROOT / "hooks/post-receive")],
                                  env=env, capture_output=True, text=True)
        self.assertNotEqual(rejected.returncode, 0, rejected.stdout + rejected.stderr)
        self.assertIn("symlink", rejected.stdout + rejected.stderr)
        self.assertFalse((work / "leak.txt").is_symlink())
        self.assertFalse((work / "leak.txt").exists())
        self.assertFalse((app / "build-ran").exists())
        self.assertEqual((work / "index.html").read_text(), "<h1>Safe</h1>")
        # Move main after its tree has been inspected, before files are deployed.
        unsafe_sha = self.git("--git-dir", str(repo), "rev-parse", "main").stdout.strip()
        self.git("--git-dir", str(repo), "update-ref", "refs/heads/main", safe_sha)
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        git_wrapper = bin_dir / "git"
        git_wrapper.write_text(
            "#!/usr/bin/env python3\n"
            "import subprocess, sys\n"
            f"command = {[shutil.which('git')]!r} + sys.argv[1:]\n"
            "result = subprocess.run(command, capture_output=True)\n"
            "if 'ls-tree' in sys.argv:\n"
            f"    subprocess.run({[shutil.which('git'), '--git-dir', str(repo), 'update-ref', 'refs/heads/main', unsafe_sha]!r}, check=True)\n"
            "sys.stdout.buffer.write(result.stdout)\n"
            "sys.stderr.buffer.write(result.stderr)\n"
            "sys.exit(result.returncode)\n")
        git_wrapper.chmod(0o755)
        env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]
        moved = subprocess.run(["bash", str(ROOT / "hooks/post-receive")],
                               env=env, capture_output=True, text=True)
        self.assertEqual(moved.returncode, 0, moved.stdout + moved.stderr)
        self.assertFalse((work / "leak.txt").exists())
        self.assertFalse((work / "leak.txt").is_symlink())

    def test_concurrent_hooks_deploy_newer_content_last(self):
        repo = self.root / "content.git"
        source = self.root / "source"
        work = self.root / "public-docs"
        app = self.root / "app"
        work.mkdir()
        app.mkdir()
        (app / "build.py").write_text(
            "from pathlib import Path\n"
            f"content = Path({str(work / 'index.html')!r}).read_text()\n"
            "with Path('built-content').open('a') as log:\n"
            "    log.write(content + '\\n')\n")
        self.git("init", "--bare", str(repo))
        self.git("init", "-b", "main", str(source))
        self.git("-C", str(source), "config", "user.name", "Docsite test")
        self.git("-C", str(source), "config", "user.email", "test@example.com")
        (source / "index.html").write_text("older content")
        self.git("-C", str(source), "add", ".")
        self.git("-C", str(source), "commit", "-m", "older content")
        self.git("-C", str(source), "push", str(repo), "main")

        inspected = self.root / "inspected"
        release = self.root / "release"
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        git_wrapper = bin_dir / "git"
        git_wrapper.write_text(
            "#!/usr/bin/env python3\n"
            "import os, subprocess, sys, time\n"
            "from pathlib import Path\n"
            f"result = subprocess.run({[shutil.which('git')]!r} + sys.argv[1:], capture_output=True)\n"
            "if 'ls-tree' in sys.argv and os.environ.get('HOOK_ORDER') == 'older':\n"
            f"    Path({str(inspected)!r}).touch()\n"
            "    deadline = time.monotonic() + 10\n"
            f"    while not Path({str(release)!r}).exists():\n"
            "        if time.monotonic() > deadline:\n"
            "            sys.exit('test barrier timed out')\n"
            "        time.sleep(0.01)\n"
            "sys.stdout.buffer.write(result.stdout)\n"
            "sys.stderr.buffer.write(result.stderr)\n"
            "sys.exit(result.returncode)\n")
        git_wrapper.chmod(0o755)
        env = {**os.environ, "DOCSITE_REPO": str(repo),
               "DOCSITE_WORK": str(work), "DOCSITE_ROOT": str(app),
               "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]}
        hook = ["bash", str(ROOT / "hooks/post-receive")]
        older = subprocess.Popen(hook, env={**env, "HOOK_ORDER": "older"},
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        newer = None
        try:
            deadline = time.monotonic() + 10
            while not inspected.exists():
                if older.poll() is not None or time.monotonic() > deadline:
                    self.fail("older hook did not reach the validation barrier")
                time.sleep(0.01)
            (source / "index.html").write_text("newer content")
            self.git("-C", str(source), "add", ".")
            self.git("-C", str(source), "commit", "-m", "newer content")
            self.git("-C", str(source), "push", str(repo), "main")
            newer = subprocess.Popen(hook, env={**env, "HOOK_ORDER": "newer"},
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(newer.stdout.readline().strip(),
                             "[docsite post-receive] deploying...")
            # An unlocked newer hook completes while the older hook is paused.
            # A locked hook waits; release the older hook after this bounded wait.
            try:
                newer.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            release.touch()
            older_out, older_err = older.communicate(timeout=10)
            newer_out, newer_err = newer.communicate(timeout=10)
            self.assertEqual(older.returncode, 0, older_out + older_err)
            self.assertEqual(newer.returncode, 0, newer_out + newer_err)
            self.assertEqual((work / "index.html").read_text(), "newer content")
            self.assertEqual((app / "built-content").read_text().splitlines(),
                             ["older content", "newer content"])

            # Build failures still propagate, and release the deployment lock.
            (app / "build.py").write_text("raise SystemExit(17)\n")
            failed = subprocess.run(hook, env=env, capture_output=True,
                                    text=True, timeout=10)
            self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
            self.assertIn("build FAILED", failed.stdout)
            (app / "build.py").write_text("print('build recovered')\n")
            recovered = subprocess.run(hook, env=env, capture_output=True,
                                       text=True, timeout=10)
            self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
            self.assertIn("build recovered", (app / "build.log").read_text())
        finally:
            release.touch()
            for process in (older, newer):
                if process is not None:
                    if process.poll() is None:
                        process.kill()
                    process.communicate()

    @staticmethod
    def git(*args):
        return subprocess.run(["git", *args], check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
