# Mapping a test-automation repo (Playwright, Cypress, Selenium, API/load tests, BDD)

The reader needs to know: what is tested, how a run starts, what setup happens before tests, how tests are structured, and where results go.

## What to establish
- **Runner config:** `playwright.config.*`, `cypress.config.*`, `wdio.conf.*`, `pytest.ini`/`conftest.py`, `testng.xml`. Read it fully: projects/browsers, base URLs per environment, retries, workers, timeouts, reporters, global setup/teardown.
- **Layers:** tests/specs → page objects or screen/component helpers → fixtures/hooks → API clients/utilities → test data. Identify which layers exist and where.
- **Setup and auth:** global setup, stored auth state (e.g. Playwright `storageState`), seeded data, environment selection (env vars, config files; names only).
- **Fixtures and data:** custom fixtures (`test.extend`), factories, static JSON, DB seeding, cleanup strategy.
- **Targets:** which application(s)/environments are under test and how they are reached.
- **Execution:** local commands, tags/grep for suites (smoke/regression), sharding and parallelism, CI triggers (PR, nightly, deploy hooks).
- **Reporting and observability:** HTML/Allure/JUnit reports, traces/videos/screenshots, artifact upload, notifications, any telemetry/metrics export.
- **Suite shape:** count of spec files per area (the scan gives `test_file_count`; group by folder for the map).

## Diagrams to produce
- **L0:** CI trigger / developer → test runner → application under test (per environment) → reports and artifacts.
- **L1:** layered structure (specs → page objects → fixtures → utilities → data/config) with real folders.
- **L2 (pick 1-3):** *one test run end to end* as a `sequenceDiagram` (config load → global setup/auth → worker starts → fixture setup → test → teardown → reporter); *CI pipeline* (trigger → install → shard → run → merge reports → publish); *test data lifecycle*.

## Where to look
Runner config, `fixtures/`, `pages/` or `page-objects/`, `utils/`, `data/`, `.github/workflows/`, `package.json` scripts, reporter config.

## Common traps
Don't describe the app under test as if it's in this repo; draw it as an external system. Tests often share state through fixtures/global setup. Call out ordering or data dependencies in `gotchas`.
