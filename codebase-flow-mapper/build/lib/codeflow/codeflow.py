#!/usr/bin/env python3
"""codeflow: turn any repository into a layered, shareable HTML onboarding page.

Model-agnostic. The scripts are plain Python (3.9+, standard library only); any AI model can
supply the one judgement-heavy step (writing the spec JSON).

  codeflow.py map    <repo>                 complete map via an OpenAI-compatible API
  codeflow.py scan   <repo>                 evidence for a model: scan.json + graph.json
  codeflow.py pack   <repo>                 one file to paste into ANY chat model
  codeflow.py render <spec.json> --repo R   spec JSON -> HTML page (verifies cited paths)
  codeflow.py install <tool>                add instructions for an AI tool to a project
  codeflow.py build-skill                   package the Claude skill (.skill)

See PLAYBOOK.md for the full instructions a model follows.
"""
import argparse
import json
import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

VERSION = "0.2.0"
SKILL_NAME = "codebase-flow-mapper"
SKILL_DESCRIPTION = (
    "Reads any repository (frontend, backend, test automation, infra, data pipeline, monorepo, library, mobile) "
    "and produces a single self-contained HTML onboarding page with layered flow diagrams, a 'start here' reading "
    "order, a component table, a glossary and 'where to change things'. Use whenever someone is new to a codebase, "
    "asks 'how does this repo work', 'explain this codebase', 'map/diagram this repo', or wants an architecture "
    "overview, onboarding guide, dependency map or flow chart of a project, even if they never say 'diagram' or 'HTML'."
)
BEGIN, END = "<!-- codeflow:begin -->", "<!-- codeflow:end -->"


def bundled_file(name):
    """Find a bundled resource in an installed package or the source checkout."""
    for path in (os.path.join(HERE, name), os.path.join(ROOT, name)):
        if os.path.isfile(path):
            return path
    return os.path.join(HERE, name)


# ----------------------------------------------------------------------------- scan
def cmd_scan(argv):
    import import_graph
    import scan_repo
    ap = argparse.ArgumentParser(prog="codeflow.py scan")
    ap.add_argument("repo")
    ap.add_argument("--out", default=".codeflow", help="output folder (default ./.codeflow)")
    ap.add_argument("--depth", type=int, default=2, help="folder depth that defines a graph node")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.repo)
    if not os.path.isdir(root):
        sys.exit("not a directory: " + root)
    scan = scan_repo.scan(root)
    graph = import_graph.build_graph(root, args.depth, 20)
    os.makedirs(args.out, exist_ok=True)
    for name, data in (("scan.json", scan), ("graph.json", graph)):
        with open(os.path.join(args.out, name), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    types = ", ".join("%s(%d)" % (t["type"], t["score"]) for t in scan["repo_type_signals"]) or "unclassified"
    print("scanned %d files in %s" % (scan["total_files"], scan["repo"]))
    print("repo type signals: " + types)
    print("frameworks: " + (", ".join(scan["frameworks"]) or "none detected"))
    print("graph: %d nodes, %d edges, %d cycles" % (len(graph["nodes"]), len(graph["edges"]), len(graph["dependency_cycles"])))
    print("wrote %s/scan.json and %s/graph.json" % (args.out, args.out))


# ----------------------------------------------------------------------------- adapters
def adapter_block():
    cf = HERE
    playbook = bundled_file("PLAYBOOK.md")
    return "\n".join([
        BEGIN,
        "## Codebase flow mapper",
        "Use this when asked to explain, map, document or onboard someone to a codebase "
        "(\"how does this repo work\", \"give me an architecture overview or diagram\"). "
        "It produces one self-contained HTML page with layered flow diagrams.",
        "",
        "1. Read the full instructions first: `%s`" % playbook,
        "2. Scan: `python \"%s\" scan <repo-path>` (writes `.codeflow/scan.json` and `graph.json`)" % os.path.join(cf, "codeflow.py"),
        "3. Read selectively (README, manifests, entry points, most-depended-on modules, CI), then write `spec.json` "
        "following `%s`" % os.path.join(cf, "schema", "spec.schema.json"),
        "4. Render: `python \"%s\" render spec.json --repo <repo-path> --out codebase-map.html`" % os.path.join(cf, "codeflow.py"),
        "   Fix every warning (a path warning means you cited a file that doesn't exist) and re-run.",
        "",
        "Never open `.env` or credential files. Mark anything inferred rather than seen in code as `inferred`.",
        "If you cannot run commands, ask the user to run `codeflow.py pack <repo-path>` and send you the file it writes.",
        END,
    ])


def upsert_block(path, block, frontmatter=""):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        pat = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
        if pat.search(text):
            new = pat.sub(lambda m: block, text)
            action = "updated"
        else:
            new = text.rstrip() + "\n\n" + block + "\n"
            action = "appended to"
    else:
        new = frontmatter + block + "\n"
        action = "created"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new)
    return action


def build_skill(out_dir):
    """Create out_dir/codebase-flow-mapper/ (SKILL.md + codeflow/) and out_dir/codebase-flow-mapper.skill."""
    pb = bundled_file("PLAYBOOK.md")
    if not os.path.exists(pb):
        sys.exit("packaged PLAYBOOK.md is missing")
    with open(pb, encoding="utf-8") as fh:
        playbook = fh.read()
    skill_dir = os.path.join(out_dir, SKILL_NAME)
    os.makedirs(skill_dir, exist_ok=True)
    shutil.copytree(HERE, os.path.join(skill_dir, "codeflow"), dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".codeflow"))
    for extra in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        source = bundled_file(extra)
        if os.path.exists(source):
            shutil.copy(source, skill_dir)
    front = "---\nname: %s\ndescription: %s\n---\n\n" % (SKILL_NAME, SKILL_DESCRIPTION)
    note = "> Paths in this document are relative to this skill's folder.\n\n"
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(front + note + playbook)
    archive = os.path.join(out_dir, SKILL_NAME + ".skill")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for dp, dn, fn in os.walk(skill_dir):
            dn[:] = [d for d in dn if d != "__pycache__"]
            for f in sorted(fn):
                p = os.path.join(dp, f)
                z.write(p, os.path.join(SKILL_NAME, os.path.relpath(p, skill_dir)))
    return skill_dir, archive


def cmd_install(argv):
    ap = argparse.ArgumentParser(prog="codeflow.py install")
    ap.add_argument("tool", choices=["agents", "claude", "cursor", "copilot", "gemini"],
                    help="agents = AGENTS.md (read by many coding agents); claude = Claude skill folder")
    ap.add_argument("--dir", default=".", help="project to install into (default: current directory)")
    ap.add_argument("--global", dest="glob", action="store_true", help="claude only: install for all projects")
    args = ap.parse_args(argv)
    base = os.path.abspath(args.dir)
    block = adapter_block()
    if args.tool == "claude":
        dest = os.path.join(os.path.expanduser("~"), ".claude", "skills") if args.glob else os.path.join(base, ".claude", "skills")
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir, _ = build_skill(tmp)
            target = os.path.join(dest, SKILL_NAME)
            os.makedirs(dest, exist_ok=True)
            shutil.copytree(skill_dir, target, dirs_exist_ok=True)
        print("installed Claude skill to " + target)
        return
    if args.glob:
        sys.exit("--global is only supported for 'claude'")
    if args.tool == "agents":
        path, fm = os.path.join(base, "AGENTS.md"), ""
    elif args.tool == "copilot":
        path, fm = os.path.join(base, ".github", "copilot-instructions.md"), ""
    elif args.tool == "gemini":
        path, fm = os.path.join(base, "GEMINI.md"), ""
    else:  # cursor
        path = os.path.join(base, ".cursor", "rules", "codebase-flow-mapper.mdc")
        fm = ("---\ndescription: Map and explain a codebase as a layered HTML flow-diagram page. "
              "Use when asked how a repo works or to onboard someone.\nalwaysApply: false\n---\n\n")
    print("%s %s" % (upsert_block(path, block, fm), path))


def cmd_build_skill(argv):
    ap = argparse.ArgumentParser(prog="codeflow.py build-skill")
    ap.add_argument("--out", default="dist")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    skill_dir, archive = build_skill(os.path.abspath(args.out))
    print("built %s\nbuilt %s" % (skill_dir, archive))


def cmd_map(argv):
    import map_repo
    ap = argparse.ArgumentParser(prog="codeflow map")
    ap.add_argument("repo", nargs="?", default=".", help="repository to map (default: current directory)")
    ap.add_argument("--out", default="codebase-map.html", help="generated HTML path")
    ap.add_argument("--spec-out", help="generated spec path (default: <repo>/.codeflow/spec.json)")
    ap.add_argument("--api-base-url", default=os.environ.get("CODEFLOW_API_BASE_URL", "https://api.openai.com/v1"),
                    help="OpenAI-compatible API base URL (default: CODEFLOW_API_BASE_URL or OpenAI)")
    ap.add_argument("--model", default=os.environ.get("CODEFLOW_MODEL"),
                    help="model name (default: CODEFLOW_MODEL)")
    ap.add_argument("--yes", action="store_true", help="send repository excerpts without an interactive prompt")
    args = ap.parse_args(argv)

    api_key = os.environ.get("CODEFLOW_API_KEY")
    if not api_key:
        sys.exit("Set CODEFLOW_API_KEY to your provider API key before running 'codeflow map'.")
    if not args.model:
        sys.exit("Set CODEFLOW_MODEL or pass --model with a model name supported by your API provider.")

    repo = os.path.abspath(args.repo)
    if not os.path.isdir(repo):
        sys.exit("not a directory: " + repo)
    spec_out = args.spec_out or os.path.join(repo, ".codeflow", "spec.json")
    try:
        map_repo.run_map(repo, args.out, spec_out, args.api_base_url, args.model, api_key, args.yes)
    except RuntimeError as exc:
        sys.exit(str(exc))


# ----------------------------------------------------------------------------- dispatch
def delegate(module_name, argv, prog):
    mod = __import__(module_name)
    sys.argv = [prog] + argv
    mod.main()


def main():
    cmds = {
        "map": cmd_map, "scan": cmd_scan, "install": cmd_install, "build-skill": cmd_build_skill,
        "pack": lambda a: delegate("pack_context", a, "codeflow.py pack"),
        "render": lambda a: delegate("render_html", a, "codeflow.py render"),
    }
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if len(sys.argv) > 1 else 2)
    if sys.argv[1] == "--version":
        print(VERSION)
        return
    cmd = sys.argv[1]
    if cmd not in cmds:
        sys.exit("unknown command %r; try: %s" % (cmd, ", ".join(cmds)))
    cmds[cmd](sys.argv[2:])


if __name__ == "__main__":
    main()
