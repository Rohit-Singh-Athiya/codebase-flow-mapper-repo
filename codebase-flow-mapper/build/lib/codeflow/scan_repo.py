#!/usr/bin/env python3
"""Scan a repository and print a JSON inventory used to plan the flow diagrams.

Usage: python scan_repo.py <repo_path> [--out scan.json]

The output is evidence, not conclusions: languages, manifests, frameworks, entry-point
candidates, CI/test/infra files, docs, recently active files and repo-type signals
(each with the evidence that triggered it). The model (or a human) interprets it; the script never guesses
architecture.
"""
import argparse
import collections
import fnmatch
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import git, list_files, read_text  # noqa: E402

LANG = {
    ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript",
    ".mjs": "JavaScript", ".cjs": "JavaScript", ".py": "Python", ".java": "Java",
    ".kt": "Kotlin", ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP",
    ".cs": "C#", ".swift": "Swift", ".m": "Objective-C", ".scala": "Scala", ".c": "C",
    ".h": "C/C++", ".cpp": "C++", ".sql": "SQL", ".sh": "Shell", ".ps1": "PowerShell",
    ".tf": "Terraform", ".vue": "Vue", ".svelte": "Svelte", ".dart": "Dart",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".feature": "Gherkin",
    ".robot": "Robot Framework", ".ipynb": "Jupyter",
    ".yml": "YAML", ".yaml": "YAML", ".json": "JSON", ".md": "Markdown",
}
NON_CODE = {"YAML", "JSON", "Markdown"}

MANIFEST_NAMES = {
    "package.json", "pyproject.toml", "requirements.txt", "setup.py", "setup.cfg", "Pipfile",
    "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts",
    "go.mod", "go.work", "Cargo.toml", "Gemfile", "composer.json", "pubspec.yaml",
    "Makefile", "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yaml",
    "tsconfig.json", "nx.json", "turbo.json", "pnpm-workspace.yaml", "lerna.json",
    ".env.example", "Procfile", "serverless.yml", "Pulumi.yaml", "Chart.yaml", "Jenkinsfile",
}
MANIFEST_GLOBS = ["requirements*.txt", "Dockerfile*", "*.csproj", "*.sln", "docker-compose*.yml"]

CI_GLOBS = [
    ".github/workflows/*.yml", ".github/workflows/*.yaml", ".gitlab-ci.yml", "Jenkinsfile",
    "azure-pipelines.yml", ".circleci/config.yml", "bitbucket-pipelines.yml", ".buildkite/*.yml",
    "cloudbuild.yaml",
]
TEST_CONFIG_GLOBS = [
    "playwright.config.*", "cypress.config.*", "jest.config.*", "vitest.config.*",
    "pytest.ini", "tox.ini", "wdio.conf.*", "testng.xml", "karma.conf.*", "conftest.py",
    "codecept.conf.*", "testcafe*.json", "behave.ini", "robot.yaml",
]
TEST_FILE_RES = [
    re.compile(r"\.(spec|test)\.[jt]sx?$"), re.compile(r"^test_.*\.py$"), re.compile(r"_test\.py$"),
    re.compile(r"_test\.go$"), re.compile(r"(Test|Tests|IT)\.(java|kt)$"),
    re.compile(r"\.feature$"), re.compile(r"\.robot$"), re.compile(r"Tests?\.cs$"),
]
DOC_GLOBS = [
    "README*", "CONTRIBUTING*", "ARCHITECTURE*", "DESIGN*", "CODEOWNERS", "docs/*.md",
    "doc/*.md", "docs/**/*.md",
]
API_GLOBS = ["openapi*", "swagger*", "*.proto", "*.graphql", "*.gql", "schema.prisma"]

FRAMEWORK_DEPS = {
    "react": "React", "next": "Next.js", "vue": "Vue", "nuxt": "Nuxt", "@angular/core": "Angular",
    "svelte": "Svelte", "solid-js": "Solid", "vite": "Vite", "webpack": "Webpack",
    "tailwindcss": "Tailwind CSS", "storybook": "Storybook", "@storybook/react": "Storybook",
    "redux": "Redux", "@reduxjs/toolkit": "Redux Toolkit", "zustand": "Zustand",
    "express": "Express", "fastify": "Fastify", "@nestjs/core": "NestJS", "koa": "Koa",
    "hono": "Hono", "graphql": "GraphQL", "@apollo/server": "Apollo Server",
    "prisma": "Prisma", "@prisma/client": "Prisma", "typeorm": "TypeORM",
    "mongoose": "Mongoose", "sequelize": "Sequelize",
    "@playwright/test": "Playwright", "playwright": "Playwright", "cypress": "Cypress",
    "jest": "Jest", "vitest": "Vitest", "mocha": "Mocha", "webdriverio": "WebdriverIO",
    "puppeteer": "Puppeteer", "testcafe": "TestCafe", "@cucumber/cucumber": "Cucumber",
    "allure-playwright": "Allure", "k6": "k6", "artillery": "Artillery",
    "react-native": "React Native", "expo": "Expo", "electron": "Electron",
    "@opentelemetry/api": "OpenTelemetry", "lerna": "Lerna", "nx": "Nx", "turbo": "Turborepo",
}
TEXT_KEYWORDS = {
    "django": "Django", "flask": "Flask", "fastapi": "FastAPI", "pytest": "pytest",
    "selenium": "Selenium", "airflow": "Airflow", "dagster": "Dagster", "prefect": "Prefect",
    "pandas": "pandas", "pyspark": "PySpark", "dbt": "dbt", "celery": "Celery",
    "sqlalchemy": "SQLAlchemy", "pydantic": "Pydantic", "torch": "PyTorch",
    "tensorflow": "TensorFlow", "spring-boot": "Spring Boot", "testng": "TestNG",
    "junit": "JUnit", "rest-assured": "REST Assured", "cucumber": "Cucumber",
    "gin-gonic": "Gin", "gorilla/mux": "gorilla/mux", "labstack/echo": "Echo",
    "gofiber": "Fiber", "rails": "Rails", "laravel": "Laravel", "symfony": "Symfony",
    "actix": "Actix", "axum": "Axum", "tokio": "Tokio", "microsoft.aspnetcore": "ASP.NET Core",
    "xunit": "xUnit", "nunit": "NUnit", "specflow": "SpecFlow", "playwright": "Playwright",
    "robotframework": "Robot Framework", "behave": "behave", "locust": "Locust",
    "kafka": "Kafka", "rabbitmq": "RabbitMQ", "redis": "Redis", "flutter": "Flutter",
}

FRONTEND_FW = {"React", "Next.js", "Vue", "Nuxt", "Angular", "Svelte", "Solid", "Vite", "Tailwind CSS", "Storybook"}
BACKEND_FW = {"Express", "Fastify", "NestJS", "Koa", "Hono", "Apollo Server", "Django", "Flask", "FastAPI",
              "Spring Boot", "Gin", "Echo", "Fiber", "Rails", "Laravel", "Symfony", "ASP.NET Core",
              "gorilla/mux", "Actix", "Axum"}
TEST_FW = {"Playwright", "Cypress", "Selenium", "WebdriverIO", "Puppeteer", "TestCafe", "TestNG",
           "REST Assured", "Cucumber", "SpecFlow", "Robot Framework", "behave", "k6", "Locust", "Artillery"}
DATA_FW = {"Airflow", "Dagster", "Prefect", "dbt", "PySpark", "pandas"}
MOBILE_FW = {"React Native", "Expo", "Flutter"}

ENTRY_NAMES = {
    "main.ts", "main.js", "main.py", "main.go", "main.rs", "main.java", "main.kt", "main.tsx",
    "index.ts", "index.js", "index.tsx", "index.jsx", "app.ts", "app.js", "app.py", "app.tsx",
    "server.ts", "server.js", "server.py", "cli.ts", "cli.js", "cli.py", "manage.py", "wsgi.py",
    "asgi.py", "__main__.py", "Program.cs", "Startup.cs",
}
ENTRY_RES = [re.compile(r"Application\.(java|kt)$")]
CONTAINER_DIRS = {"apps", "packages", "services", "libs", "modules", "projects", "plugins", "tools"}


def matches_any(path, globs):
    base = os.path.basename(path)
    for g in globs:
        if fnmatch.fnmatch(path, g) or ("/" not in g and fnmatch.fnmatch(base, g)):
            return True
    return False


def matches_any_ci(path, globs):
    low = path.lower()
    base = os.path.basename(low)
    for g in globs:
        gl = g.lower()
        if fnmatch.fnmatchcase(low, gl) or ("/" not in gl and fnmatch.fnmatchcase(base, gl)):
            return True
    return False


TESTISH = re.compile(r"(^|/)(tests?|spec|__tests__|e2e|examples?|docs?|fixtures?|scripts|benchmarks?)(/|$)")


def scrub_url(url):
    return re.sub(r"//[^/@]+@", "//", url or "")


def detect_text_keywords(text):
    found = set()
    low = text.lower()
    for key, label in TEXT_KEYWORDS.items():
        if re.search(r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])", low):
            found.add(label)
    return found


def parse_package_json(root, rel):
    try:
        data = json.loads(read_text(root, rel) or "{}")
    except ValueError:
        return None
    deps = {}
    for k in ("dependencies", "devDependencies", "peerDependencies"):
        deps.update(data.get(k) or {})
    scripts = {k: str(v)[:140] for k, v in list((data.get("scripts") or {}).items())[:30]}
    ws = data.get("workspaces")
    if isinstance(ws, dict):
        ws = ws.get("packages")
    return {
        "path": rel, "name": data.get("name"), "private": data.get("private", False),
        "main": data.get("main") or data.get("module"), "bin": data.get("bin"),
        "has_exports": bool(data.get("exports")), "type": data.get("type"),
        "workspaces": ws, "scripts": scripts, "dependency_names": sorted(deps)[:80],
    }


def scan(root):
    """Return the inventory dict for the repository at `root`."""
    files = list_files(root)
    lang_files = collections.Counter()
    lang_loc = collections.Counter()
    dir_stats = collections.defaultdict(lambda: {"files": 0, "loc": 0, "langs": collections.Counter()})
    manifests, ci, test_configs, docs, api_files, infra = [], [], [], [], [], []
    package_jsons, entry_candidates = [], []
    test_files = 0
    tf_count = 0
    frameworks, evidence = set(), collections.defaultdict(list)
    dockerfile_cmds = []
    read_budget = 25000

    for rel in files:
        base = os.path.basename(rel)
        ext = os.path.splitext(base)[1].lower()
        lang = LANG.get(ext)
        parts = rel.split("/")

        if lang:
            lang_files[lang] += 1
            loc = 0
            if read_budget > 0 and lang not in ("JSON",):
                text = read_text(root, rel, limit=600_000)
                loc = text.count("\n") + (1 if text else 0)
                read_budget -= 1
            lang_loc[lang] += loc
            key = parts[0] if len(parts) > 1 else "."
            ds = dir_stats[key]
            ds["files"] += 1
            ds["loc"] += loc
            if lang not in NON_CODE:
                ds["langs"][lang] += 1
            if len(parts) > 2 and parts[0] in CONTAINER_DIRS:
                key2 = "/".join(parts[:2])
                ds2 = dir_stats[key2]
                ds2["files"] += 1
                ds2["loc"] += loc
                if lang not in NON_CODE:
                    ds2["langs"][lang] += 1

        if base in MANIFEST_NAMES or matches_any(rel, MANIFEST_GLOBS):
            manifests.append(rel)
        if matches_any(rel, CI_GLOBS):
            ci.append(rel)
        if matches_any(rel, TEST_CONFIG_GLOBS):
            test_configs.append(rel)
        if any(r.search(base) for r in TEST_FILE_RES) or (
                lang and lang not in NON_CODE and re.search(r"(^|/)(tests?|spec|__tests__|e2e)(/|$)", rel)):
            test_files += 1
        if matches_any(rel, API_GLOBS):
            api_files.append(rel)
        if len(parts) <= 3 and matches_any_ci(rel, DOC_GLOBS):
            docs.append(rel)
        if ext == ".tf":
            tf_count += 1
        if base in ("Chart.yaml", "serverless.yml", "Pulumi.yaml", "cloudbuild.yaml") or \
                re.match(r"(playbook|site).*\.ya?ml$", base):
            infra.append(rel)
        if parts[0] in ("k8s", "kubernetes", "helm", "terraform", "ansible", "infra", "infrastructure", "deploy"):
            infra.append(rel)

        depth = len(parts) - 1
        if (base in ENTRY_NAMES and (not base.startswith("index.") or depth <= 2)) or \
                any(r.search(base) for r in ENTRY_RES):
            entry_candidates.append((1 if TESTISH.search(rel) else 0, depth, rel))

        if base == "package.json" and len(package_jsons) < 80:
            pj = parse_package_json(root, rel)
            if pj:
                package_jsons.append(pj)
        if base.startswith("Dockerfile"):
            text = read_text(root, rel, limit=100_000)
            for line in text.splitlines():
                if re.match(r"\s*(CMD|ENTRYPOINT)\b", line, re.I):
                    dockerfile_cmds.append({"file": rel, "line": line.strip()[:160]})

        manifest_text_names = ("requirements", "pyproject.toml", "Pipfile", "setup.py", "pom.xml",
                               "build.gradle", "go.mod", "Gemfile", "composer.json", "Cargo.toml",
                               "pubspec.yaml")
        if base.endswith(".csproj") or any(base.startswith(n) for n in manifest_text_names):
            for fw in detect_text_keywords(read_text(root, rel, limit=200_000)):
                frameworks.add(fw)
                evidence[fw].append(rel)

    for pj in package_jsons:
        for dep in pj["dependency_names"]:
            fw = FRAMEWORK_DEPS.get(dep)
            if fw:
                frameworks.add(fw)
                evidence[fw].append(pj["path"])

    # ---- repo-type signals (evidence-backed) ----
    signals = collections.defaultdict(list)
    for fw in frameworks:
        if fw in FRONTEND_FW:
            signals["frontend"].append("framework: " + fw)
        if fw in BACKEND_FW:
            signals["backend"].append("framework: " + fw)
        if fw in TEST_FW:
            signals["test-automation"].append("framework: " + fw)
        if fw in DATA_FW:
            signals["data-pipeline"].append("framework: " + fw)
        if fw in MOBILE_FW:
            signals["mobile"].append("framework: " + fw)
    for cfg in test_configs:
        if re.search(r"(playwright|cypress|wdio|testcafe|codecept|testng)", cfg):
            signals["test-automation"].append("config: " + cfg)
    code_files = sum(n for l, n in lang_files.items() if l not in NON_CODE)
    ratio_note = None
    if code_files and test_files / float(code_files) > 0.4:
        ratio_note = "%d of %d source files are tests" % (test_files, code_files)
    if lang_files["Vue"] or lang_files["Svelte"]:
        signals["frontend"].append("Vue/Svelte files present")
    if tf_count:
        signals["infra"].append("%d Terraform files" % tf_count)
    if infra:
        signals["infra"].append("infra files, e.g. " + infra[0])
    if lang_files["Jupyter"] or lang_files["SQL"] > 20:
        signals["data-pipeline"].append("notebooks / heavy SQL")
    if any(p.startswith(("android/", "ios/")) for p in files[:5000]):
        signals["mobile"].append("android/ or ios/ folders")
    sub_manifests = [m for m in manifests if "/" in m and os.path.basename(m) in
                     ("package.json", "pyproject.toml", "go.mod", "Cargo.toml", "pom.xml", "build.gradle")]
    if any(m in manifests for m in ("pnpm-workspace.yaml", "nx.json", "turbo.json", "lerna.json", "go.work")) \
            or any(pj.get("workspaces") for pj in package_jsons):
        signals["monorepo"].append("workspace config present")
    if len(sub_manifests) >= 3:
        signals["monorepo"].append("%d nested package manifests" % len(sub_manifests))
    # A high test ratio only supports "test-automation" when something else does too;
    # many well-tested libraries have lots of unit tests but are not test-automation repos.
    if ratio_note and signals.get("test-automation"):
        signals["test-automation"].append(ratio_note)

    app_types = ("frontend", "backend", "mobile", "data-pipeline", "infra")
    no_app = not any(signals.get(t) for t in app_types)
    root_pj = next((p for p in package_jsons if p["path"] == "package.json"), None)
    if root_pj and root_pj.get("name") and not root_pj["private"] and no_app:
        signals["library"].append("publishable npm package (root package.json is not private)")
    if no_app and any(m in manifests for m in ("pyproject.toml", "setup.py", "setup.cfg")):
        meta = read_text(root, "pyproject.toml", limit=200_000) if "pyproject.toml" in manifests else ""
        if "[project]" in meta or "[build-system]" in meta or "setup.py" in manifests or "setup.cfg" in manifests:
            signals["library"].append("Python packaging metadata at the root")
    if no_app and "go.mod" in manifests and not any(p.endswith("main.go") for p in files):
        signals["library"].append("Go module with no main package")

    repo_types = sorted(({"type": t, "score": len(v), "evidence": v[:6]} for t, v in signals.items()),
                        key=lambda x: -x["score"])

    # ---- structure ----
    structure = []
    for key, ds in dir_stats.items():
        structure.append({
            "path": key, "files": ds["files"], "loc": ds["loc"],
            "languages": [l for l, _ in ds["langs"].most_common(3)],
        })
    structure.sort(key=lambda x: -x["loc"])

    # ---- git facts ----
    git_info = {}
    head = git(root, "log", "-1", "--format=%h|%cI|%s")
    if head:
        h, d, s = (head.split("|", 2) + ["", ""])[:3]
        git_info = {
            "commit": h, "date": d, "subject": s[:120],
            "branch": git(root, "rev-parse", "--abbrev-ref", "HEAD"),
            "remote": scrub_url(git(root, "config", "--get", "remote.origin.url")),
        }
        churn = git(root, "log", "--since=6 months ago", "--name-only", "--pretty=format:", timeout=40)
        counts = collections.Counter(l for l in churn.splitlines() if l.strip())
        fileset_now = set(files)
        hot = [{"path": p, "commits": c} for p, c in counts.most_common(15) if p in fileset_now and c > 1]
        if hot:
            git_info["most_changed_last_6_months"] = hot

    entry_candidates.sort()
    result = {
        "repo": os.path.basename(root), "root": root, "total_files": len(files),
        "git": git_info,
        "languages": [{"language": l, "files": lang_files[l], "loc": lang_loc[l]}
                      for l, _ in sorted(lang_loc.items(), key=lambda kv: -kv[1])],
        "repo_type_signals": repo_types,
        "frameworks": sorted(frameworks),
        "framework_evidence": {k: sorted(set(v))[:3] for k, v in evidence.items()},
        "structure": structure[:60],
        "manifests": sorted(manifests)[:80],
        "package_json": package_jsons[:40],
        "entry_point_candidates": [p for _, _, p in entry_candidates[:40]],
        "dockerfile_commands": dockerfile_cmds[:10],
        "ci_files": sorted(ci),
        "test_configs": sorted(test_configs),
        "test_file_count": test_files,
        "infra_files": sorted(set(infra))[:30],
        "api_contract_files": sorted(api_files)[:20],
        "docs": sorted(docs)[:30],
        "notes": [
            "Entry points are candidates; confirm by reading them.",
            "Repo-type signals list their evidence; a repo can have several types.",
        ],
    }
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--out")
    args = ap.parse_args()
    root = os.path.abspath(args.repo)
    if not os.path.isdir(root):
        sys.exit("not a directory: " + root)
    result = scan(root)
    out = json.dumps(result, indent=2)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(out)
        print("wrote %s (%d files scanned)" % (args.out, result["total_files"]), file=sys.stderr)
    else:
        print(out)


if __name__ == "__main__":
    main()
