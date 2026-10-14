#!/usr/bin/env python3
"""Build a single markdown "context pack" that any chat model can work from.

For models that cannot run commands or open files: the pack holds the instructions,
the scan and dependency-graph evidence, a list of real paths, short excerpts of the files
that matter, and the output schema. Paste or upload it, and the model replies with spec JSON.

Privacy: excerpts of your source are included unless --structure-only is used, and common
secret formats are redacted. Treat the pack like the code itself before sending it anywhere.
"""
import fnmatch
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import list_files, read_text  # noqa: E402
import import_graph  # noqa: E402
import scan_repo  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

GUIDE_FOR_TYPE = {
    "frontend": "frontend.md", "backend": "backend.md", "test-automation": "test-automation.md",
    "infra": "infra-ci.md", "data-pipeline": "data-pipeline.md", "monorepo": "monorepo.md",
    "library": "other.md", "mobile": "other.md",
}
NEVER_INCLUDE = [".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*",
                 "*credentials*", "*secret*", ".npmrc", ".pypirc", "*.keystore", "*.jks"]
SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "<redacted private key>"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "<redacted aws key id>"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "<redacted github token>"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "<redacted slack token>"),
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "<redacted api key>"),
    (re.compile(r"(?i)((?:api[_-]?key|secret|token|passw(?:or)?d|auth)[\w-]*\s*[:=]\s*['\"]?)[^\s'\"#,;]{8,}"),
     r"\1<redacted>"),
    (re.compile(r"(?i)(://[^/\s:@]+:)[^/\s@]+@"), r"\1<redacted>@"),
]
LANG_TAG = {".py": "python", ".ts": "ts", ".tsx": "tsx", ".js": "js", ".jsx": "jsx", ".json": "json",
            ".yml": "yaml", ".yaml": "yaml", ".toml": "toml", ".go": "go", ".java": "java",
            ".kt": "kotlin", ".md": "markdown", ".xml": "xml", ".sh": "bash", ".tf": "hcl"}


def redact(text):
    for pat, repl in SECRET_PATTERNS:
        text = pat.sub(repl, text)
    return text


def blocked(rel):
    base = os.path.basename(rel).lower()
    return any(fnmatch.fnmatch(base, p) for p in NEVER_INCLUDE)


def clip(text, cap):
    if len(text) <= cap:
        return text
    cut = text[:cap]
    if "\n" in cut:
        cut = cut.rsplit("\n", 1)[0]
    return cut + "\n[... truncated to fit the size budget ...]"


def package_json_summary(raw):
    try:
        d = json.loads(raw)
    except ValueError:
        return None
    out = ["name: %s" % d.get("name", "?")]
    for k in ("description", "version", "main", "module", "type", "bin", "workspaces", "engines", "private"):
        if d.get(k) not in (None, "", {}, []):
            out.append("%s: %s" % (k, json.dumps(d[k], separators=(",", ":"))[:200]))
    if d.get("scripts"):
        out.append("scripts:")
        out += ["  %s: %s" % (k, str(v)[:160]) for k, v in list(d["scripts"].items())[:25]]
    for k in ("dependencies", "devDependencies", "peerDependencies"):
        if d.get(k):
            out.append("%s (names): %s" % (k, ", ".join(sorted(d[k])[:60])))
    return "\n".join(out)


def excerpt(root, rel, max_lines, cap):
    if blocked(rel):
        return ""
    raw = read_text(root, rel, limit=400_000)
    if not raw.strip():
        return ""
    if os.path.basename(rel) == "package.json":
        summ = package_json_summary(raw)
        if summ:
            return clip("#### `%s` (summary of the fields that matter)\n```\n%s\n```" % (rel, redact(summ)), cap)
    lines = redact(raw).splitlines()
    body = "\n".join(lines[:max_lines])
    note = "" if len(lines) <= max_lines else "\n[... %d more lines ...]" % (len(lines) - max_lines)
    tag = LANG_TAG.get(os.path.splitext(rel)[1].lower(), "")
    return clip("#### `%s`\n```%s\n%s%s\n```" % (rel, tag, body, note), cap)


def best_file_for_node(root, files, node):
    prefix = "" if node == "." else node + "/"
    cands = [f for f in files if f.startswith(prefix) and "/" not in f[len(prefix):]
             and os.path.splitext(f)[1].lower() in (".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".java", ".kt")]
    for pat in ("index.*", "main.*", "app.*", "server.*", "__init__.py", "mod.*"):
        for f in cands:
            if fnmatch.fnmatch(os.path.basename(f), pat) and os.path.getsize(os.path.join(root, f)) > 120:
                return f
    cands.sort(key=lambda f: -os.path.getsize(os.path.join(root, f)))
    return cands[0] if cands else None


TESTISH = re.compile(r"(^|/)(tests?|spec|__tests__|e2e|examples?|docs?|fixtures?|benchmarks?)(/|$)")


def file_tree(files, max_lines=200):
    """Paths a model may cite. Source folders first; tests, examples and docs last and shorter."""
    by_top = {}
    for f in files:
        by_top.setdefault(f.split("/")[0] if "/" in f else ".", []).append(f)
    lines = []
    root_files = sorted(by_top.pop(".", []))
    if root_files:
        lines.append("(repository root files) " + ", ".join(root_files[:30]))
    tops = sorted(by_top, key=lambda t: (bool(TESTISH.search(t + "/")), -len(by_top[t])))
    for t in tops:
        fs = by_top[t]
        low = bool(TESTISH.search(t + "/"))
        lines.append("%s/  (%d files)" % (t, len(fs)))
        subs = {}
        for f in fs:
            if f.count("/") >= 2:
                key = "/".join(f.split("/")[:2])
                subs[key] = subs.get(key, 0) + 1
        for key, n in sorted(subs.items(), key=lambda kv: -kv[1])[: (3 if low else 10)]:
            lines.append("%s/  (%d files)" % (key, n))
        for f in sorted(x for x in fs if x.count("/") == 1)[: (3 if low else 16)]:
            lines.append(f)
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["[... more paths omitted ...]"]
    return "\n".join(lines)


def read_playbook():
    for cand in (os.path.join(HERE, "PLAYBOOK.md"), os.path.join(ROOT, "PLAYBOOK.md"),
                 os.path.join(ROOT, "SKILL.md")):
        if os.path.exists(cand):
            with open(cand, encoding="utf-8") as fh:
                text = fh.read()
            return re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S).strip()
    return ""


def read_asset(rel):
    p = os.path.join(HERE, rel)
    if not os.path.exists(p):
        return ""
    with open(p, encoding="utf-8") as fh:
        return fh.read().strip()


def trimmed_scan(scan):
    L = ["repo: %s (%d files)" % (scan["repo"], scan["total_files"])]
    L.append("languages: " + ", ".join("%s %d files" % (l["language"], l["files"]) for l in scan["languages"][:8]))
    L.append("repo type signals: " + ("; ".join("%s [%s]" % (t["type"], "; ".join(t["evidence"][:3]))
                                               for t in scan["repo_type_signals"]) or "none matched"))
    L.append("frameworks: " + (", ".join(scan["frameworks"]) or "none detected"))
    L.append("entry point candidates: " + ", ".join(scan["entry_point_candidates"][:12]))
    L.append("CI files: " + (", ".join(scan["ci_files"][:10]) or "none"))
    L.append("test configs: %s; test files: %d" % (", ".join(scan["test_configs"][:8]) or "none", scan["test_file_count"]))
    if scan["infra_files"]:
        L.append("infra files: " + ", ".join(scan["infra_files"][:8]))
    if scan["api_contract_files"]:
        L.append("API contract files: " + ", ".join(scan["api_contract_files"][:8]))
    L.append("docs: " + (", ".join(scan["docs"][:12]) or "none"))
    if scan["dockerfile_commands"]:
        L.append("container commands: " + "; ".join("%s: %s" % (d["file"], d["line"]) for d in scan["dockerfile_commands"][:3]))
    ch = scan.get("git", {}).get("most_changed_last_6_months")
    if ch:
        L.append("most changed in the last 6 months: " + ", ".join("%s (%d)" % (c["path"], c["commits"]) for c in ch[:8]))
    L.append("structure (path: files, lines of code, languages):")
    for x in scan["structure"][:22]:
        L.append("  %s: %d files, %d loc, %s" % (x["path"], x["files"], x["loc"], "/".join(x["languages"]) or "-"))
    return "\n".join(L)


def graph_section(graph):
    low = lambda s: bool(TESTISH.search(s + "/"))
    nodes = sorted(graph["nodes"], key=lambda n: (low(n["id"]), -n["files"]))[:30]
    out = ["Nodes (folder, files, imported-by, imports, top external packages):"]
    for n in nodes:
        out.append("- %s (%d files, fan_in %d, fan_out %d) %s" % (
            n["id"], n["files"], n["fan_in"], n["fan_out"], ", ".join(n["top_external_packages"][:4])))
    out.append("\nEdges (importer -> imported, import count):")
    for e in sorted(graph["edges"], key=lambda e: (low(e["from"]) or low(e["to"]), -e["imports"]))[:60]:
        out.append("- %s -> %s (%d)" % (e["from"], e["to"], e["imports"]))
    if graph["dependency_cycles"]:
        out.append("\nDependency cycles: " + "; ".join(" <-> ".join(c) for c in graph["dependency_cycles"][:5]))
    out.append("\nCaveat: " + graph["caveats"][0])
    out.append("\nStarter Mermaid for the component map (rename into human terms):\n```mermaid\n%s\n```" % graph["starter_mermaid"])
    return "\n".join(out)


def build_pack(root, max_chars=60000, structure_only=False, depth=2):
    root = os.path.abspath(root)
    files = list_files(root)
    scan = scan_repo.scan(root)
    graph = import_graph.build_graph(root, depth, 20)

    types = [t["type"] for t in scan["repo_type_signals"]]
    guides, seen = [], set()
    for t in types or ["other"]:
        g = GUIDE_FOR_TYPE.get(t, "other.md")
        if g not in seen:
            seen.add(g)
            text = read_asset(os.path.join("references", g))
            if text:
                guides.append(text)
    if not guides:
        guides.append(read_asset(os.path.join("references", "other.md")))

    schema = read_asset(os.path.join("schema", "spec.schema.json"))
    example = read_asset(os.path.join("schema", "example-spec.json"))
    playbook = read_playbook()

    header = [
        "# Codebase context pack: %s" % scan["repo"],
        "",
        "> Generated by `codeflow.py pack`. You are the model. Everything you need is in this file; you cannot "
        "run commands or open other files. **Reply with ONLY one JSON object** that matches the schema near the "
        "end (no prose, no code fences around it).",
        "",
        "## Your task",
        "Follow the playbook below in **Mode B (chat only)**. Cite only paths that appear in this pack "
        "(the path list, file excerpts, scan data or graph). If you must refer to something you cannot see, mark it "
        "`\"confidence\": \"inferred\"` or put it under `open_questions`. A person will run the renderer next; "
        "it reports any cited path that doesn't exist, and they may paste those warnings back to you to fix.",
        "",
        "## Playbook", playbook, "",
        "## Guidance for this repo's type(s): %s" % (", ".join(types) or "unclassified"),
        "\n\n".join(guides), "",
    ]
    tail = [
        "## Output schema (JSON Schema)", "```json", schema, "```", "",
        "## Minimal example of a valid reply", "```json", example, "```", "",
        "## Reminder", "Return ONLY the JSON object. Quote every Mermaid label, keep each diagram under about 15 nodes, "
        "and include a `components` table for every diagram.",
    ]
    fixed = "\n".join(header + tail)
    budget = max(max_chars - len(fixed), 8000)

    sections = []  # (title, body, weight)
    sections.append(("Scan summary", "```\n%s\n```" % trimmed_scan(scan), 0.13))
    sections.append(("Paths you may cite (directories to depth 3, files to depth 2)", "```\n%s\n```" % file_tree(files), 0.09))
    sections.append(("Dependency graph (folder level)", graph_section(graph), 0.15))

    if not structure_only:
        def collect(paths, max_lines, per_cap):
            return "\n\n".join(x for x in (excerpt(root, p, max_lines, per_cap) for p in paths) if x)

        readmes = sorted([d for d in scan["docs"] if os.path.basename(d).lower().startswith("readme")],
                         key=lambda p: (p.count("/"), len(p)))[:1]
        manifests = [m for m in scan["manifests"] if m.count("/") == 0 and
                     os.path.basename(m) not in (".env.example", "tsconfig.json")][:6]
        entries = scan["entry_point_candidates"][:8]
        ci = scan["ci_files"][:4]
        tcfg = scan["test_configs"][:3]
        top_nodes = [n["node"] for n in graph["most_depended_on"][:6]]
        tops = []
        for n in top_nodes:
            f = best_file_for_node(root, files, n)
            if f and f not in entries:
                tops.append(f)
        sections += [
            ("README (excerpt)", collect(readmes, 120, 5000), 0.12),
            ("Manifests and run scripts", collect(manifests, 70, 2200), 0.10),
            ("Entry points", collect(entries, 70, 2600), 0.15),
            ("CI workflows", collect(ci, 70, 2400), 0.07),
            ("Test and runner configuration", collect(tcfg, 60, 2400), 0.05),
            ("Most depended-on modules (one representative file each)", collect(tops, 60, 2400), 0.14),
        ]
    else:
        header.insert(3, "> Structure-only pack: no source excerpts are included. Mark anything you cannot see as inferred.")
        fixed = "\n".join(header + tail)

    parts = list(header)
    for title, body, weight in sections:
        if not body.strip():
            continue
        parts += ["## " + title, clip(body, int(budget * weight)), ""]
    parts += tail
    return "\n".join(parts)


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("repo")
    ap.add_argument("--out", default=os.path.join(".codeflow", "context-pack.md"))
    ap.add_argument("--max-chars", type=int, default=60000, help="rough size budget (about 4 chars per token)")
    ap.add_argument("--structure-only", action="store_true", help="omit all source excerpts")
    ap.add_argument("--depth", type=int, default=2)
    args = ap.parse_args()
    text = build_pack(args.repo, args.max_chars, args.structure_only, args.depth)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("wrote %s (%d chars, about %d tokens)" % (args.out, len(text), len(text) // 4), file=sys.stderr)


if __name__ == "__main__":
    main()
