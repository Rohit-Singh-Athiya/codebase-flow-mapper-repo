# Mapping a frontend repo

## What to establish
- **Shell and build:** framework (React/Next/Vue/Angular/Svelte), bundler (Vite/Webpack/Next), how to run and build it (`package.json` scripts), env/config loading.
- **Routing:** file-based (`app/`, `pages/`) or declared (router config). The route list is the best table of contents for a frontend.
- **Component structure:** pages/screens → feature components → shared UI/design system. Find where the shared primitives live.
- **State:** local state, global store (Redux/Zustand/Pinia/Context), server cache (React Query/SWR/Apollo). Where does data live and who owns it?
- **Data access:** the API client layer, base URLs, auth header injection, error handling, generated clients (OpenAPI/GraphQL codegen).
- **Auth:** where the session/token lives, route guards, login/logout flow.
- **Cross-cutting:** i18n, feature flags, analytics/telemetry, error boundaries, styling approach.

## Diagrams to produce
- **L0:** browser app ↔ backend API(s), auth provider, CDN, third-party SDKs.
- **L1:** layers (routes → features → shared UI → data layer → API client) as subgraphs, with the real folder names.
- **L2 (pick 1-3):** *page load* (route match → data fetch → render → hydrate), *auth/login*, *a key user action* (e.g. submit form → mutation → cache update → UI), *build and deploy*.

## Where to look
`src/main.*`, `src/App.*`, `app/layout.*`, router files, `src/api|services|lib`, store folders, `vite.config.*`/`next.config.*`, `.storybook/`.

## Common traps
Generated API clients and codegen output look like source but aren't; say so. Monolithic `utils/` folders hide the real dependencies, so use the import graph.
