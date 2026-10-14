# Mapping a data / ML / analytics repo

## What to establish
- **Orchestrator:** Airflow/Dagster/Prefect/dbt/Spark jobs, or plain scripts + cron. Find where schedules are defined.
- **Lineage:** sources → ingestion → raw → transform/staging → marts/features → consumers (BI, models, APIs). Build this from DAG definitions, dbt `ref()`/`source()` calls, SQL `FROM` clauses.
- **Storage:** warehouses, lakes, buckets, tables (names), schemas, partitioning.
- **Quality and ops:** tests/expectations, alerting, backfill procedures, SLAs if documented.
- **ML specifics:** training vs. inference code, feature definitions, model registry, evaluation, serving path, notebooks vs. production code.

## Diagrams to produce
- **L0:** external sources → pipeline → stores → consumers.
- **L1:** stages with the real DAG/model/package names.
- **L2:** *one pipeline run* (trigger → tasks in dependency order → outputs), or *training → registry → serving*.

## Where to look
`dags/`, `models/` (dbt), `pipelines/`, `jobs/`, `notebooks/`, `sql/`, orchestrator config, `requirements*`.

## Common traps
Notebooks hold exploratory code that may not run in production, so say which is which. Dynamic DAG generation hides tasks from static reading; mark those links inferred.
