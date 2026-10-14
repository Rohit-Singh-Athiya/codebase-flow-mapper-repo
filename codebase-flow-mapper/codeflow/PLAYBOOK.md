# Codebase flow mapper: playbook

Instructions for an AI model (any model) that has been asked to explain, map or onboard someone to a codebase. Humans can read it too; it's the canonical description of what this toolkit does.

**Goal:** produce one self-contained HTML page a new teammate can read in about 15 minutes and come away knowing what the repo is, how its parts connect, how the important things flow through it, and where to start reading.

## Why it's built in layers

One diagram of "the whole repo" is either too vague to teach anything or too dense to read, and a real repo won't fit in a model's context in one pass anyway. So the page zooms in three steps:

| Level | Diagram | Question it answers |
|---|---|---|
| 0 | System context | What is this, what does it talk to, how does it run? |
| 1 | Component map | What are the main parts and who depends on whom? |
| 2 | Flows (1-4 of them) | What happens, step by step, when the important things occur? |

Keep each diagram under about 15 nodes. If something needs more, split it. A reader can hold about that many boxes in their head.

## Pick your mode

**Mode A: you can run shell commands and read files** (coding agents and IDE assistants). Follow the workflow below. Commands use `codeflow/codeflow.py`; if your instructions give you an absolute path to it, use that.

**Mode B: chat only.** You can't run anything. A person ran `codeflow.py pack`, which gave you a *context pack*: this playbook, evidence about the repo, a list of real paths, short excerpts of key files and the output schema. Do steps 2-5 below from the pack alone and **reply with only the spec JSON**. Cite only paths that appear in the pack. The person runs the renderer next, which reports any cited path that doesn't exist; if they paste warnings back, fix them and resend the full JSON.

## Workflow

### 1. Scan (Mode A)
```bash
python codeflow/codeflow.py scan <repo>        # writes .codeflow/scan.json and .codeflow/graph.json
```
`scan.json` reports languages, frameworks, manifests, entry-point candidates, CI/test/infra files, docs, recently changed files (where the team is actively working) and **repo-type signals with their evidence**. `graph.json` is a folder-level dependency graph (JS/TS including tsconfig aliases and workspace packages, Python, Go, Java/Kotlin) with cycles and a starter Mermaid flowchart. It is regex-based, so treat it as a strong hint, not ground truth: it cannot see dependency injection, plugin registries or computed imports. If one giant node dominates, rerun with `--depth 3`.

### 2. Classify and use the matching guidance
A repo can be several things at once (a monorepo containing a web app, an API and an end-to-end suite). Use the guide for each type the scan reports, not just the top one:

| Signal | Guide |
|---|---|
| `frontend` | `codeflow/references/frontend.md` |
| `backend` | `codeflow/references/backend.md` |
| `test-automation` | `codeflow/references/test-automation.md` |
| `infra`, or heavy CI/deploy files | `codeflow/references/infra-ci.md` |
| `data-pipeline` | `codeflow/references/data-pipeline.md` |
| `monorepo` | `codeflow/references/monorepo.md` (read first, then the others per package) |
| `library`, `mobile`, CLI, or nothing matched | `codeflow/references/other.md` |

They say which flows matter for that kind of repo, so a React app and a Playwright suite are each mapped around the things that actually matter there. (In Mode B the relevant guides are already in the pack.)

### 3. Read selectively
Never try to read everything. In this order, stop when you could explain the repo to a colleague:
1. README, ARCHITECTURE/docs, CONTRIBUTING: the team's own account. Verify it against code; docs go stale.
2. Manifests and scripts (`package.json` scripts, `Makefile`, `pyproject.toml`): they show how the thing is actually run, built and tested.
3. Entry points from the scan, confirming which are real.
4. The 3-5 most depended-on nodes in the graph: the load-bearing parts.
5. CI workflows and Dockerfiles: how code reaches production, or how tests get triggered.
6. The most recently changed files: what's alive versus legacy.

Do not open `.env*`, key files or anything that looks like a credential. Say that configuration exists and how it's loaded; never copy values into the output.

### 4. Write the spec
Write `spec.json` (Mode B: your whole reply). It is the only thing you author; the template handles layout. The schema is `codeflow/schema/spec.schema.json`; a small valid example is `codeflow/schema/example-spec.json`.

Shape in brief: `repo_name`, `tagline`, `repo_types`, `stack`, `start_here[]` (path + why), `diagrams[]` (id, level 0/1/2, title, summary, mermaid, optional legend and confidence, `components[]` mapping each box to a real path and role), `where_to_change[]`, `glossary[]`, `gotchas[]`, `open_questions[]`. Aim for one level-0, one level-1 and one to four level-2 diagrams.

Writing guidance, and why:
- **Name things the way the repo does** (its folder and class names) so a reader can search for them. Add a plain-language `role` so they don't have to.
- **Mark uncertainty.** Use `"confidence": "inferred"` where you reasoned from names or structure instead of seeing code. A new hire acts on this page: a confident wrong claim costs days, an honest "inferred" costs one question.
- **Say what is NOT here** when it matters ("auth lives in a separate service"). Boundaries are what newcomers can't see.
- **Put surprises in `gotchas` and unknowns in `open_questions`** instead of guessing.
- **Every box in a diagram appears in its `components` table** with a real path.

### 5. Mermaid rules that keep diagrams rendering
- Quote every label: `A["Auth service (JWT)"]`. Unquoted parentheses, `&`, `<`, `>` or `#` break the parser.
- Use short ASCII node IDs (`api`, `db`, `q1`); put the readable text in the label.
- `flowchart LR` for architecture, `sequenceDiagram` for request or test-run flows, `stateDiagram-v2` for lifecycles.
- Group layers with `subgraph` instead of adding more boxes. Label edges with verbs ("validates", "publishes").
- Use dashed edges (`-.->`) for links you inferred, and say so in `legend`.
- No ``` fences inside the string; use `\n` for newlines in JSON.
- The graph's `starter_mermaid` is a starting point for level 1. Rename nodes into human terms and merge the noise.

### 6. Render and verify
```bash
python codeflow/codeflow.py render spec.json --repo <repo> --out codebase-map.html
```
The renderer fails on missing fields, **warns about every cited path that doesn't exist in the repo**, and lints Mermaid. Fix every warning (a path warning means you cited something you didn't verify) and rerun until clean. Then tell the person where the file is, give a 3-4 line summary of what the repo is, and list anything you marked inferred or unknown. Don't re-explain the page.

The page bundles its fonts and loads the Mermaid library from a pinned CDN version; offline it falls back to showing diagram source. For a fully offline file add `--inline-mermaid <path to mermaid.min.js>` (from `npm i mermaid`).

## The page's visual language

Keep the spec consistent with it: **dashed means inferred or unknown** (dashed tags, dashed note borders), so use dashed diagram edges for inferred links. Orange only ever marks "you are here" (current zoom level, current nav item).

## Quality bar

Before you hand it over, check:
- A newcomer could answer "where do I start reading?" and "where would I change X?" from the page alone.
- Every box in every diagram appears in a components table with a real path.
- Nothing is claimed that wasn't in the code, docs, CI or pack; guesses carry the inferred label.
- Level-2 flows follow something real (a request, a test run, a deploy, a job), not an abstract data flow.
