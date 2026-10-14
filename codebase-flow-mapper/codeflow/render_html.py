#!/usr/bin/env python3
"""Render the onboarding HTML page from a spec JSON file.

Usage:
  python render_html.py spec.json --out codebase-map.html [--repo <repo_path>] [--strict]

What it does besides filling the template:
  * validates required fields and diagram shape
  * verifies that every file/folder path the spec cites exists in the repo (--repo),
    so the page can't point a new hire at files that aren't there
  * lints Mermaid for the mistakes that most often break rendering
Exit code 1 on errors (or on warnings with --strict).
"""
import argparse
import base64
import datetime
import glob
import json
import os
import re
import sys

KNOWN_TYPES = ("flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram",
               "stateDiagram-v2", "erDiagram", "journey", "gantt", "C4Context", "mindmap",
               "timeline", "block-beta", "architecture-beta")
NODE_DEF = re.compile(r"(?<![\w\"'])([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[\[|\[\(|\(\(|\[|\(|\{|>)")


def lint_mermaid(d, warnings):
    code = d.get("mermaid", "")
    label = "diagram '%s'" % d.get("id", "?")
    first = next((l.strip() for l in code.splitlines() if l.strip() and not l.strip().startswith("%%")), "")
    kind = first.split()[0] if first else ""
    if kind not in KNOWN_TYPES:
        warnings.append("%s: first line should start with a Mermaid diagram type (got %r)" % (label, kind))
        return
    if "```" in code:
        warnings.append("%s: remove the ``` fences from the Mermaid source" % label)
    if kind in ("flowchart", "graph"):
        nodes = set(NODE_DEF.findall(code))
        if len(nodes) > 20:
            warnings.append("%s: ~%d nodes; split it, diagrams above ~15-20 nodes stop being readable"
                            % (label, len(nodes)))
        for m in re.finditer(r"\[([^\]\"\[]*)\]", code):
            inner = m.group(1)
            if re.search(r"[()<>&#;]", inner) and not inner.startswith(("/", "\\", "(")):
                warnings.append("%s: label [%s] has special characters; wrap labels in double quotes"
                                % (label, inner[:40]))
                break
        if re.search(r"-->\s*\|[^|]*\|\s*-->", code):
            warnings.append("%s: malformed edge label" % label)
    if code.count("(") != code.count(")") or code.count("[") != code.count("]"):
        warnings.append("%s: unbalanced brackets or parentheses" % label)


def collect_paths(spec):
    paths = []
    for s in spec.get("start_here", []):
        paths.append(("start_here", s.get("path")))
    for d in spec.get("diagrams", []):
        for c in d.get("components", []):
            paths.append(("diagram %s component %s" % (d.get("id"), c.get("name")), c.get("path")))
    for w in spec.get("where_to_change", []):
        for p in w.get("paths", []):
            paths.append(("where_to_change '%s'" % w.get("task"), p))
    return paths


def path_exists(repo, p):
    p = p.strip()
    if not p:
        return False
    while p.startswith("./"):  # only a literal "./" prefix; never strip the dot of ".github"
        p = p[2:]
    repo = os.path.realpath(repo)

    def inside_repo(candidate):
        try:
            common = os.path.commonpath((repo, os.path.realpath(candidate)))
            return os.path.normcase(common) == os.path.normcase(repo)
        except ValueError:
            return False

    candidate = os.path.join(repo, p)
    if any(ch in p for ch in "*?["):
        return any(inside_repo(match) for match in glob.glob(candidate, recursive=True))
    return inside_repo(candidate) and os.path.exists(candidate)


def font_css(assets_dir):
    """Embed the bundled fonts as data URIs so the page looks the same offline."""
    faces = [("Schibsted Grotesk", "schibsted-grotesk.woff2", "400 900"),
             ("JetBrains Mono", "jetbrains-mono.woff2", "100 800")]
    out = []
    for family, fname, weight in faces:
        fp = os.path.join(assets_dir, "fonts", fname)
        if not os.path.exists(fp):
            continue
        with open(fp, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        out.append('@font-face{font-family:"%s";font-style:normal;font-weight:%s;font-display:swap;'
                   'src:url(data:font/woff2;base64,%s) format("woff2");}' % (family, weight, b64))
    return "\n".join(out)


def inline_mermaid(html, path):
    """Replace the CDN <script> with the library itself so the page works offline."""
    with open(path, encoding="utf-8") as fh:
        code = fh.read().replace("</script", "<\\/script")
    tag = re.compile(r'<script src="https://cdn\.jsdelivr\.net/npm/mermaid@[^"]+" defer></script>')
    if not tag.search(html):
        sys.exit("template has no Mermaid CDN tag to replace")
    return tag.sub(lambda m: "<script>" + code + "</script>", html, count=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--out", default="codebase-map.html")
    ap.add_argument("--repo", help="repo root, used to verify cited paths exist")
    ap.add_argument("--template", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                       "assets", "report_template.html"))
    ap.add_argument("--inline-mermaid", metavar="MERMAID_JS",
                    help="path to mermaid.min.js to embed (fully offline page); e.g. node_modules/mermaid/dist/mermaid.min.js")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = ap.parse_args()

    with open(args.spec, encoding="utf-8") as fh:
        spec = json.load(fh)

    errors, warnings = [], []
    for k in ("repo_name", "tagline"):
        if not spec.get(k):
            errors.append("missing '%s'" % k)
    diagrams = spec.get("diagrams") or []
    if not diagrams:
        errors.append("need at least one diagram")
    seen = set()
    for d in diagrams:
        for k in ("id", "level", "title", "summary", "mermaid"):
            if d.get(k) in (None, ""):
                errors.append("diagram %r missing '%s'" % (d.get("id"), k))
        if d.get("id") in seen:
            errors.append("duplicate diagram id %r" % d.get("id"))
        seen.add(d.get("id"))
        if d.get("level") not in (0, 1, 2):
            errors.append("diagram %r: level must be 0, 1 or 2" % d.get("id"))
        if d.get("mermaid"):
            lint_mermaid(d, warnings)
    if not any(d.get("level") == 0 for d in diagrams):
        warnings.append("no level-0 (system context) diagram; new readers need the big picture first")
    if not spec.get("start_here"):
        warnings.append("no 'start_here' reading list")

    checked = missing = 0
    if args.repo:
        repo = os.path.abspath(args.repo)
        for where, p in collect_paths(spec):
            if not p:
                continue
            checked += 1
            if not path_exists(repo, p):
                missing += 1
                warnings.append("path not found in repo: %s (%s)" % (p, where))

    if not spec.get("generated_from"):
        spec["generated_from"] = "Generated %s" % datetime.date.today().isoformat()

    for e in errors:
        print("ERROR:   " + e, file=sys.stderr)
    for w in warnings:
        print("WARNING: " + w, file=sys.stderr)
    if errors or (warnings and args.strict):
        sys.exit(1)

    with open(args.template, encoding="utf-8") as fh:
        tpl = fh.read()
    # '<' escaped so spec text can never close the <script> tag
    blob = json.dumps(spec, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    if "__SPEC_JSON__" not in tpl:
        sys.exit("template is missing the __SPEC_JSON__ placeholder")
    assets_dir = os.path.dirname(os.path.abspath(args.template))
    html = tpl.replace("__SPEC_JSON__", blob).replace("/*__FONTS__*/", font_css(assets_dir))
    if args.inline_mermaid:
        html = inline_mermaid(html, args.inline_mermaid)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(html)
    msg = "wrote %s (%d diagrams" % (args.out, len(diagrams))
    if args.repo:
        msg += "; %d/%d cited paths verified" % (checked - missing, checked)
    print(msg + ")", file=sys.stderr)


if __name__ == "__main__":
    main()
