"""Shared helpers for the codebase-flow-mapper scripts (stdlib only)."""
import os
import subprocess

# Directories that never contain hand-written source worth mapping.
IGNORE_DIRS = {
    ".git", "node_modules", "dist", "build", "out", ".next", ".nuxt", ".svelte-kit",
    "target", "vendor", "venv", ".venv", "env", "__pycache__", ".gradle", ".idea",
    ".vscode", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "coverage",
    "playwright-report", "test-results", "allure-results", "allure-report",
    ".terraform", ".cache", ".parcel-cache", ".turbo", ".nx", "obj", "Pods",
    "DerivedData", "site-packages", ".dart_tool", "bower_components",
}

# Hidden directories that are worth looking at (CI, tooling config).
KEEP_DOT_DIRS = {".github", ".gitlab", ".circleci", ".husky", ".devcontainer", ".buildkite"}


def _ignored(parts):
    for part in parts:
        if part in IGNORE_DIRS:
            return True
        if part.startswith(".") and part not in KEEP_DOT_DIRS:
            return True
    return False


def list_files(root, max_files=60000):
    """Return repo-relative file paths using '/' separators.

    Prefers `git ls-files` (respects .gitignore); falls back to a directory walk.
    """
    root = os.path.abspath(root)
    files = []
    try:
        out = subprocess.run(
            ["git", "-C", root, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True, timeout=60,
        )
        if out.returncode == 0 and out.stdout:
            for p in out.stdout.decode("utf-8", "replace").split("\0"):
                if not p:
                    continue
                parts = p.split("/")
                if _ignored(parts[:-1]):
                    continue
                if os.path.isfile(os.path.join(root, p)):
                    files.append(p)
                if len(files) >= max_files:
                    break
            if files:
                return files
    except Exception:
        pass

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in IGNORE_DIRS and (not d.startswith(".") or d in KEEP_DOT_DIRS)
        ]
        rel_dir = os.path.relpath(dirpath, root)
        for name in filenames:
            rel = name if rel_dir == "." else os.path.join(rel_dir, name)
            files.append(rel.replace(os.sep, "/"))
            if len(files) >= max_files:
                return files
    return files


def read_text(root, rel_path, limit=1_000_000):
    """Read a text file; return '' for binary, huge or unreadable files."""
    full = os.path.join(root, rel_path)
    try:
        if os.path.getsize(full) > limit:
            return ""
        with open(full, "rb") as fh:
            data = fh.read()
        if b"\0" in data[:4096]:
            return ""
        return data.decode("utf-8", "replace")
    except Exception:
        return ""


def git(root, *args, timeout=30):
    """Run a git command in root; return stdout text or ''."""
    try:
        out = subprocess.run(["git", "-C", root] + list(args), capture_output=True, timeout=timeout)
        if out.returncode == 0:
            return out.stdout.decode("utf-8", "replace").strip()
    except Exception:
        pass
    return ""
