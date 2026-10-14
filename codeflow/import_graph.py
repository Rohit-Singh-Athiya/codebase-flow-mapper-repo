#!/usr/bin/env python3
"""Build a folder-level dependency graph from source imports (stdlib only).

Usage: python import_graph.py <repo_path> [--depth 2] [--out graph.json]

Supports JS/TS (incl. tsconfig path aliases and workspace packages), Python, Go and
Java/Kotlin. Regex-based, so it is approximate (dynamic imports built from variables are
invisible) but deterministic and fast. Output: nodes, weighted edges, fan-in/out leaders,
dependency cycles, top external packages per node, and a starter Mermaid flowchart.
"""
import argparse
import collections
import json
import os
import pkgutil
import re
import sys
import sysconfig

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import list_files, read_text  # noqa: E402

JS_EXT = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"}
JS_TRY = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte", ".json"]
JS_RE = re.compile(
    r"""(?:import|export)\s+(?:type\s+)?(?:[^'"`;]*?\s+from\s+)?['"]([^'"]+)['"]"""
    r"""|require\(\s*['"]([^'"]+)['"]\s*\)|import\(\s*['"]([^'"]+)['"]\s*\)"""
)
NODE_BUILTINS = {"fs", "path", "os", "http", "https", "crypto", "util", "events", "stream",
                 "child_process", "url", "zlib", "assert", "buffer", "net", "tls", "readline",
                 "worker_threads", "perf_hooks", "timers", "process", "module", "vm", "dns"}
PY_IMPORT = re.compile(r"^\s*import\s+([\w\.]+(?:\s*,\s*[\w\.]+)*)", re.M)
PY_FROM = re.compile(r"^[ \t]*from[ \t]+(\.*)([\w\.]*)[ \t]+import[ \t]+(\([^)]*\)|[\w\*, \t\\]+)", re.M)
if hasattr(sys, "stdlib_module_names"):
    STDLIB = sys.stdlib_module_names
else:
    STDLIB = set(sys.builtin_module_names)
    STDLIB.update(name for _, name, _ in pkgutil.iter_modules([sysconfig.get_paths()["stdlib"]]))
GO_BLOCK = re.compile(r"import\s*\(([^)]*)\)", re.S)
GO_ONE = re.compile(r'^\s*import\s+(?:[\w\.]+\s+)?"([^"]+)"', re.M)
GO_LINE = re.compile(r'"([^"]+)"')
JAVA_PKG = re.compile(r"^\s*package\s+([\w\.]+)", re.M)
JAVA_IMP = re.compile(r"^\s*import\s+(?:static\s+)?([\w\.]+?)(\.\*)?\s*;?\s*$", re.M)


def strip_json_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(^|\s)//[^\n]*", r"\1", text)


def node_of(path, depth):
    parts = path.split("/")[:-1]
    return "/".join(parts[:depth]) if parts else "."


def build_graph(root, depth=2, max_nodes=20, auto=True):
    """Return the folder-level dependency graph dict for the repository at `root`.

    With auto=True the node depth increases while one folder holds most of the (non-test) code, and a
    flat package that folders cannot split is shown file by file, so the graph stays informative."""
    files = list_files(root)
    fileset = set(files)
    src = [f for f in files if os.path.splitext(f)[1].lower() in
           JS_EXT | {".py", ".go", ".java", ".kt"}]
    testish = re.compile(r"(^|/)(tests?|spec|__tests__|e2e|examples?|docs?|fixtures?)(/|$)")

    def dominant(d):
        c = collections.Counter(node_of(f, d) for f in src if not testish.search(f))
        total = sum(c.values())
        if not total:
            return None, 0, 0.0
        n, k = c.most_common(1)[0]
        return n, k, k / float(total)

    file_level = None
    if auto:
        d = depth
        while d < 8:
            n, k, share = dominant(d)
            if n is None or share < 0.6 or k < 8:
                break
            inside = [f for f in src if node_of(f, d) == n]
            nd = d + 1  # skip single-child folder chains (src/main/java/org/...) until the code splits
            while nd <= 8 and len({node_of(f, nd) for f in inside}) <= 1:
                nd += 1
            if nd <= 8:
                d = nd
                continue
            if sum(1 for f in inside if f.endswith(".go")) * 2 < len(inside):
                file_level = n  # flat package: one node per file
            break
        depth = d

    def nodeof(path):
        n = node_of(path, depth)
        return path if (file_level is not None and n == file_level) else n

    node_files = collections.Counter()
    node_loc = collections.Counter()
    edges = collections.Counter()
    external = collections.defaultdict(collections.Counter)

    # ---------- indexes ----------
    # workspace packages: package name -> directory
    pkg_dirs = {}
    for f in files:
        if os.path.basename(f) == "package.json":
            try:
                name = json.loads(read_text(root, f) or "{}").get("name")
            except ValueError:
                name = None
            if name:
                pkg_dirs[name] = os.path.dirname(f) or "."
    # tsconfig aliases
    aliases = []  # (prefix, [target_dir_prefixes], has_wildcard)
    base_urls = []  # directories bare imports may resolve from
    for f in files:
        b = os.path.basename(f)
        if re.match(r"(ts|js)config(\..*)?\.json$", b):
            try:
                cfg = json.loads(strip_json_comments(read_text(root, f)) or "{}")
            except ValueError:
                continue
            co = cfg.get("compilerOptions") or {}
            tsdir = os.path.dirname(f)
            base = os.path.normpath(os.path.join(tsdir, co.get("baseUrl", "."))) if co.get("baseUrl") else None
            if base:
                base_urls.append(base.replace("\\", "/"))
            for pat, targets in (co.get("paths") or {}).items():
                wild = pat.endswith("*")
                prefix = pat[:-1] if wild else pat
                tdirs = []
                for t in targets:
                    t = t[:-1] if t.endswith("*") else t
                    norm = os.path.normpath(os.path.join(tsdir, co.get("baseUrl", "."), t)).replace("\\", "/")
                    # normpath drops the trailing slash that separates a wildcard prefix from the rest
                    tdirs.append(norm.rstrip("/") + "/" if (wild and t.endswith("/")) else norm)
                aliases.append((prefix, tdirs, wild))

    py_index = {}
    java_index = {}
    java_pkg_dirs = {}
    go_mods = {}
    for f in src:
        ext = os.path.splitext(f)[1]
        if ext == ".py":
            parts = f[:-3].split("/")
            if parts[-1] == "__init__":
                parts = parts[:-1]
            if not parts:
                continue
            # package root = first ancestor directory without __init__.py
            i = len(f.split("/")) - 1
            d = os.path.dirname(f)
            while d and (d + "/__init__.py") in fileset:
                d = os.path.dirname(d)
            rel = f[len(d) + 1:] if d else f
            rp = rel[:-3].split("/")
            if rp[-1] == "__init__":
                rp = rp[:-1]
            for dotted in {".".join(rp), ".".join(parts), ".".join(parts[1:]) if parts[0] in ("src", "lib") else None}:
                if dotted and dotted not in py_index:
                    py_index[dotted] = f
        elif ext in (".java", ".kt"):
            m = JAVA_PKG.search(read_text(root, f, limit=100_000)[:4000])
            if m:
                fq = m.group(1) + "." + os.path.splitext(os.path.basename(f))[0]
                java_index[fq] = f
                java_pkg_dirs.setdefault(m.group(1), f)
    for f in files:
        if os.path.basename(f) == "go.mod":
            m = re.search(r"^module\s+(\S+)", read_text(root, f, limit=50_000), re.M)
            if m:
                go_mods[m.group(1)] = os.path.dirname(f) or "."

    # ---------- resolvers ----------
    def try_js_path(cand):
        cand = cand.replace("\\", "/")
        if cand in fileset:
            return cand
        stem = re.sub(r"\.(m|c)?jsx?$", "", cand)  # TS often imports './x.js' for x.ts
        for c in (cand, stem):
            for e in JS_TRY:
                if c + e in fileset:
                    return c + e
            for e in JS_TRY:
                if c + "/index" + e in fileset:
                    return c + "/index" + e
        return None

    def package_name(spec):
        parts = spec.split("/")
        return "/".join(parts[:2]) if spec.startswith("@") else parts[0]

    def resolve_js(f, spec):
        """Return ('file', path) | ('dir', path) | ('ext', name) | None."""
        if spec.startswith("."):
            r = try_js_path(os.path.normpath(os.path.join(os.path.dirname(f), spec)))
            return ("file", r) if r else None
        for prefix, tdirs, wild in aliases:
            if (wild and spec.startswith(prefix)) or (not wild and spec == prefix):
                rest = spec[len(prefix):] if wild else ""
                for t in tdirs:
                    r = try_js_path(t + rest if wild else t)
                    if r:
                        return ("file", r)
        pk = package_name(spec)
        if pk in pkg_dirs:
            return ("dir", pkg_dirs[pk])
        for b in base_urls:
            r = try_js_path(os.path.normpath(os.path.join(b, spec)))
            if r:
                return ("file", r)
        if spec.startswith("node:") or pk in NODE_BUILTINS:
            return None
        return ("ext", pk)

    def resolve_py_abs(mod):
        parts = mod.split(".")
        for n in range(len(parts), 0, -1):
            hit = py_index.get(".".join(parts[:n]))
            if hit:
                return hit
        return None

    def add_edge(src_node, dst_node):
        if src_node != dst_node:
            edges[(src_node, dst_node)] += 1

    # ---------- walk ----------
    for f in src:
        ext = os.path.splitext(f)[1].lower()
        text = read_text(root, f, limit=800_000)
        if not text:
            continue
        me = nodeof(f)
        node_files[me] += 1
        node_loc[me] += text.count("\n") + 1

        if ext in JS_EXT:
            for m in JS_RE.finditer(text):
                spec = m.group(1) or m.group(2) or m.group(3)
                if not spec:
                    continue
                r = resolve_js(f, spec)
                if not r:
                    continue
                kind, val = r
                if kind == "file":
                    add_edge(me, nodeof(val))
                elif kind == "dir":
                    add_edge(me, "/".join(val.split("/")[:depth]) if val != "." else ".")
                else:
                    external[me][val] += 1
        elif ext == ".py":
            for m in PY_IMPORT.finditer(text):
                for mod in re.split(r"\s*,\s*", m.group(1)):
                    hit = resolve_py_abs(mod)
                    if hit:
                        add_edge(me, nodeof(hit))
                    else:
                        top = mod.split(".")[0]
                        if top not in STDLIB:
                            external[me][top] += 1
            for m in PY_FROM.finditer(text):
                dots, mod, names = m.group(1), m.group(2), m.group(3)
                if dots:
                    base = os.path.dirname(f)
                    for _ in range(len(dots) - 1):
                        base = os.path.dirname(base)
                    cands = []
                    rel = os.path.join(base, mod.replace(".", "/")) if mod else base
                    cands += [rel + ".py", rel + "/__init__.py"]
                    for n in re.split(r"[\s,()\\]+", names):
                        if n and n != "*":
                            cands += [os.path.join(rel, n) + ".py"]
                    for c in cands:
                        c = os.path.normpath(c).replace("\\", "/")
                        if c in fileset:
                            add_edge(me, nodeof(c))
                            break
                else:
                    hit = resolve_py_abs(mod)
                    if not hit:
                        for n in re.split(r"[\s,()\\]+", names):
                            if n and n != "*":
                                hit = py_index.get(mod + "." + n)
                                if hit:
                                    break
                    if hit:
                        add_edge(me, nodeof(hit))
                    elif mod.split(".")[0] not in STDLIB and mod:
                        external[me][mod.split(".")[0]] += 1
        elif ext == ".go":
            specs = []
            for blk in GO_BLOCK.findall(text):
                specs += GO_LINE.findall(blk)
            specs += GO_ONE.findall(text)
            for s in specs:
                hit = None
                for mod, mdir in go_mods.items():
                    if s == mod or s.startswith(mod + "/"):
                        sub = s[len(mod):].strip("/")
                        d = (mdir + "/" + sub).strip("./") if mdir != "." else sub
                        hit = d or "."
                        break
                if hit is not None:
                    add_edge(me, "/".join(hit.split("/")[:depth]) if hit != "." else ".")
                elif "." in s.split("/")[0]:
                    external[me]["/".join(s.split("/")[:3])] += 1
        elif ext in (".java", ".kt"):
            for m in JAVA_IMP.finditer(text):
                fq, wild = m.group(1), m.group(2)
                hit = None
                if wild:
                    hit = java_pkg_dirs.get(fq)
                else:
                    parts = fq.split(".")
                    for n in range(len(parts), 1, -1):
                        hit = java_index.get(".".join(parts[:n]))
                        if hit:
                            break
                if hit:
                    add_edge(me, nodeof(hit))
                else:
                    external[me][".".join(fq.split(".")[:2])] += 1

    # ---------- analysis ----------
    nodes = sorted(node_files)
    fan_in, fan_out = collections.Counter(), collections.Counter()
    adj = collections.defaultdict(set)
    for (a, b), n in edges.items():
        fan_out[a] += 1
        fan_in[b] += 1
        adj[a].add(b)

    # Tarjan SCC for cycles
    sys.setrecursionlimit(10000)
    index, low, on, stack, sccs, counter = {}, {}, set(), [], [], [0]

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in adj.get(v, ()):
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                sccs.append(sorted(comp))

    for v in list(adj):
        if v not in index:
            strong(v)

    # starter mermaid: most-connected nodes
    degree = {n: fan_in[n] + fan_out[n] for n in nodes}
    top = [n for n, d in sorted(degree.items(), key=lambda kv: -kv[1]) if d > 0][: max_nodes]
    ids = {n: "n%d" % i for i, n in enumerate(top)}
    lines = ["flowchart LR"]
    for n in top:
        label = n if len(n) <= 30 else "\u2026/" + "/".join(n.split("/")[-2:])
        lines.append('  %s["%s"]' % (ids[n], label.replace('"', "'")))
    shown = sorted(((a, b, c) for (a, b), c in edges.items() if a in ids and b in ids),
                   key=lambda x: -x[2])[:40]
    for a, b, c in shown:
        lines.append("  %s --> %s" % (ids[a], ids[b]))

    result = {
        "repo": os.path.basename(root), "depth": depth, "file_level_for": file_level,
        "source_files_analysed": len(src),
        "nodes": [{"id": n, "files": node_files[n], "loc": node_loc[n],
                   "fan_in": fan_in[n], "fan_out": fan_out[n],
                   "top_external_packages": [k for k, _ in external[n].most_common(6)]} for n in nodes],
        "edges": [{"from": a, "to": b, "imports": c} for (a, b), c in edges.most_common(400)],
        "most_depended_on": [{"node": n, "fan_in": c} for n, c in fan_in.most_common(8)],
        "most_dependencies": [{"node": n, "fan_out": c} for n, c in fan_out.most_common(8)],
        "dependency_cycles": sccs,
        "starter_mermaid": "\n".join(lines),
        "caveats": ["Regex-based: dynamic/computed imports and runtime wiring "
                    "(DI containers, plugin registries) are not visible here."],
    }
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--depth", type=int, default=2, help="folder depth that defines a node")
    ap.add_argument("--out")
    ap.add_argument("--fixed-depth", action="store_true", help="do not auto-adjust depth")
    ap.add_argument("--max-nodes", type=int, default=20, help="nodes in the starter Mermaid")
    args = ap.parse_args()
    root = os.path.abspath(args.repo)
    result = build_graph(root, args.depth, args.max_nodes, not args.fixed_depth)
    nodes, edges = result["nodes"], result["edges"]
    out = json.dumps(result, indent=2)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(out)
        print("wrote %s: %d nodes, %d edges" % (args.out, len(nodes), len(edges)), file=sys.stderr)
    else:
        print(out)


if __name__ == "__main__":
    main()
