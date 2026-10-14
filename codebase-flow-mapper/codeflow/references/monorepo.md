# Mapping a monorepo

Read this before the per-type references; the job is to avoid describing every package at the same depth.

## Strategy
1. **Inventory packages:** workspace config (`pnpm-workspace.yaml`, `workspaces`, `nx.json`, `turbo.json`, `go.work`, Cargo workspace) and the scan's `package_json` list. Give each package one line: what it is, apps vs. libraries.
2. **Package graph:** run the import graph with `--depth 2` (so `apps/web`, `packages/ui` are nodes). That is your level-1 diagram. Show apps on the left/top, shared libs below.
3. **Pick depth deliberately:** map the 2-4 most important apps/services in level-2 flows; list the rest in the components table without their own diagrams. Say so in `open_questions` ("not mapped in detail: ...") rather than silently omitting them.
4. **Build orchestration:** how tasks run across packages (Nx/Turbo/Lerna/Make), caching, "affected" builds, shared tooling config (eslint/tsconfig base).
5. **Ownership and boundaries:** CODEOWNERS, enforced import rules, shared contracts between apps.

## Diagrams to produce
- **L0:** the whole product: its apps/services, external systems, deploy targets.
- **L1:** package/app dependency graph (apps → feature libs → shared libs).
- **L2:** one or two cross-package flows (e.g. a user action touching web → API → shared lib), plus the CI/build flow.

## Common traps
Workspace packages imported by name (`@org/ui`) are resolved by the import graph script; check `top_external_packages` isn't hiding internal packages that failed to resolve. Generated or vendored packages inflate node counts.
