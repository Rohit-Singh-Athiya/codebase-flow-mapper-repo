"""Smoke and regression tests. Standard library only: python3 -m unittest discover -s tests -v"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CF = os.path.join(ROOT, "codeflow", "codeflow.py")
DEMO = os.path.join(ROOT, "examples", "demo-repo")
SPEC = os.path.join(ROOT, "examples", "demo-spec.json")


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def run(*args, cwd=None, env=None):
    return subprocess.run([sys.executable, CF] + list(args), capture_output=True, text=True, cwd=cwd, env=env)


class ScanAndGraph(unittest.TestCase):
    def test_scan_classifies_demo(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = run("scan", DEMO, "--out", tmp)
            self.assertEqual(r.returncode, 0, r.stderr)
            scan = load(os.path.join(tmp, "scan.json"))
            types = {t["type"] for t in scan["repo_type_signals"]}
            self.assertTrue({"backend", "test-automation"} <= types, types)
            self.assertIn("Playwright", scan["frameworks"])

    def test_graph_resolves_tsconfig_alias_and_python_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            run("scan", DEMO, "--out", tmp)
            graph = load(os.path.join(tmp, "graph.json"))
            edges = {(e["from"], e["to"]): e["imports"] for e in graph["edges"]}
            self.assertIn(("src/services", "src/db"), edges)   # via the @db/* alias
            self.assertEqual(edges.get(("worker", "worker/jobs")), 2)  # absolute + relative import


class Render(unittest.TestCase):
    def render(self, spec, extra=()):
        with tempfile.TemporaryDirectory() as tmp:
            sp = os.path.join(tmp, "spec.json")
            write(sp, json.dumps(spec))
            out = os.path.join(tmp, "out.html")
            r = run("render", sp, "--repo", DEMO, "--out", out, "--strict", *extra)
            html = read(out) if os.path.exists(out) else ""
            return r, html

    def test_demo_spec_renders_clean(self):
        r, html = self.render(load(SPEC))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("demo-checkout", html)
        self.assertIn("@font-face", html)

    def test_invented_path_is_rejected(self):
        spec = load(SPEC)
        spec["start_here"].append({"path": "src/does/not/exist.ts", "why": "made up"})
        r, _ = self.render(spec)
        self.assertEqual(r.returncode, 1)
        self.assertIn("path not found", r.stderr)

    def test_dot_directories_are_not_mangled(self):
        # regression: lstrip("./") turned ".github" into "github"
        spec = load(SPEC)
        spec["start_here"].append({"path": ".github/workflows/e2e.yml", "why": "CI"})
        r, _ = self.render(spec)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_spec_text_cannot_break_out_of_the_page(self):
        spec = load(SPEC)
        spec["tagline"] = "</script><script>alert(1)</script>"
        r, html = self.render(spec)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(html.count("<script>alert(1)"), 0)

    def test_unquoted_mermaid_label_warns(self):
        spec = load(SPEC)
        spec["diagrams"][0]["mermaid"] = "flowchart LR\n  a[Auth (JWT)] --> b[\"ok\"]"
        r, _ = self.render(spec)
        self.assertEqual(r.returncode, 1)
        self.assertIn("special characters", r.stderr)

    def test_parent_directory_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            os.mkdir(repo)
            with open(os.path.join(tmp, "outside.txt"), "w", encoding="utf-8") as fh:
                fh.write("outside")
            spec = load(SPEC)
            spec["start_here"] = [{"path": "../outside.txt", "why": "outside the repository"}]
            spec_path = os.path.join(tmp, "spec.json")
            write(spec_path, json.dumps(spec))
            result = run("render", spec_path, "--repo", repo, "--out", os.path.join(tmp, "out.html"), "--strict")
            self.assertEqual(result.returncode, 1)
            self.assertIn("path not found in repo: ../outside.txt", result.stderr)


class Pack(unittest.TestCase):
    def test_pack_has_sections_and_redacts_secrets(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as out:
            write(os.path.join(repo, "README.md"),
                  "# Demo\nAPI_KEY=abcd1234efgh5678ijkl9999\nDB at postgres://user:hunter2pass@db/x\n")
            write(os.path.join(repo, ".env"), "SECRET_TOKEN=do-not-leak-me-12345\n")
            write(os.path.join(repo, "package.json"), json.dumps({"name": "demo", "scripts": {"start": "node index.js"}}))
            write(os.path.join(repo, "index.js"), "console.log('hi')\n")
            pack = os.path.join(out, "pack.md")
            r = run("pack", repo, "--out", pack)
            self.assertEqual(r.returncode, 0, r.stderr)
            text = read(pack)
            for section in ("## Playbook", "## Scan summary", "## Output schema", "## Minimal example"):
                self.assertIn(section, text)
            for leaked in ("abcd1234efgh5678ijkl9999", "hunter2pass", "do-not-leak-me-12345"):
                self.assertNotIn(leaked, text)

    def test_structure_only_has_no_source(self):
        with tempfile.TemporaryDirectory() as out:
            pack = os.path.join(out, "pack.md")
            r = run("pack", DEMO, "--structure-only", "--out", pack)
            self.assertEqual(r.returncode, 0, r.stderr)
            text = read(pack)
            # strings that exist only in the demo's source files (the example reply also mentions createOrder)
            self.assertNotIn("pay.example.com", text)
            self.assertNotIn("new PrismaClient", text)
            self.assertIn("Structure-only", text)


class Install(unittest.TestCase):
    def test_agents_install_is_idempotent_and_keeps_existing_text(self):
        with tempfile.TemporaryDirectory() as proj:
            path = os.path.join(proj, "AGENTS.md")
            write(path, "# Notes\nKeep tests green.\n")
            for _ in range(2):
                self.assertEqual(run("install", "agents", "--dir", proj).returncode, 0)
            text = read(path)
            self.assertEqual(text.count("codeflow:begin"), 1)
            self.assertIn("Keep tests green.", text)

    def test_every_target_writes_its_file(self):
        expected = {"agents": "AGENTS.md", "copilot": ".github/copilot-instructions.md", "gemini": "GEMINI.md",
                    "cursor": ".cursor/rules/codebase-flow-mapper.mdc",
                    "claude": ".claude/skills/codebase-flow-mapper/SKILL.md"}
        with tempfile.TemporaryDirectory() as proj:
            for tool, rel in expected.items():
                self.assertEqual(run("install", tool, "--dir", proj).returncode, 0, tool)
                self.assertTrue(os.path.exists(os.path.join(proj, rel)), tool)

    def test_build_skill_is_self_contained(self):
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(run("build-skill", "--out", out).returncode, 0)
            skill = os.path.join(out, "codebase-flow-mapper")
            head = read(os.path.join(skill, "SKILL.md")).split("---")[1]
            self.assertIn("name: codebase-flow-mapper", head)
            self.assertTrue(os.path.exists(os.path.join(skill, "codeflow", "codeflow.py")))
            self.assertTrue(os.path.exists(os.path.join(out, "codebase-flow-mapper.skill")))

    def test_build_skill_preserves_custom_files(self):
        with tempfile.TemporaryDirectory() as out:
            custom_dir = os.path.join(out, "codebase-flow-mapper")
            os.makedirs(custom_dir)
            marker = os.path.join(custom_dir, "my-notes.txt")
            write(marker, "Keep this file.")
            self.assertEqual(run("build-skill", "--out", out).returncode, 0)
            self.assertEqual(read(marker), "Keep this file.")

    def test_packaged_resources_match_source_documents(self):
        for name in ("PLAYBOOK.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
            self.assertEqual(read(os.path.join(ROOT, name)), read(os.path.join(ROOT, "codeflow", name)), name)


class OneCommandMap(unittest.TestCase):
    def test_map_calls_api_and_writes_html(self):
        response_body = json.dumps({
            "choices": [{"message": {"content": json.dumps(load(SPEC))}}],
        }).encode("utf-8")
        seen = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                seen["path"] = self.path
                seen["authorization"] = self.headers.get("Authorization")
                seen["request"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(response_body)

            def log_message(self, fmt, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                html_path = os.path.join(tmp, "map.html")
                spec_path = os.path.join(tmp, "spec.json")
                env = os.environ.copy()
                env["CODEFLOW_API_KEY"] = "test-key"
                result = run(
                    "map", DEMO, "--api-base-url", "http://127.0.0.1:%d/v1" % server.server_port,
                    "--model", "test-model", "--out", html_path, "--spec-out", spec_path, "--yes", env=env,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(os.path.isfile(html_path))
                self.assertTrue(os.path.isfile(spec_path))
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

        self.assertEqual(seen["path"], "/v1/chat/completions")
        self.assertEqual(seen["authorization"], "Bearer test-key")
        self.assertEqual(seen["request"]["model"], "test-model")
        self.assertIn("## Playbook", seen["request"]["messages"][1]["content"])


if __name__ == "__main__":
    unittest.main()
