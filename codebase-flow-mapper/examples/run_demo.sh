#!/usr/bin/env bash
# Runs the whole pipeline on the bundled demo repo and writes examples/output/codebase-map.html
# Needs only Python 3.9+. Works the same no matter which AI model you use for the "write the spec" step.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
cf="python3 $here/../codeflow/codeflow.py"
out="$here/output"
mkdir -p "$out"

echo "1/3 scan: evidence for a model (scan.json, graph.json)"
$cf scan "$here/demo-repo" --out "$out"
echo "2/3 pack: the single file you would paste into a chat model"
$cf pack "$here/demo-repo" --out "$out/context-pack.md"
echo "3/3 render: spec.json -> HTML (here the spec is pre-written; a model writes it in real use)"
$cf render "$here/demo-spec.json" --repo "$here/demo-repo" --strict --out "$out/codebase-map.html"
echo "done: $out/codebase-map.html"
