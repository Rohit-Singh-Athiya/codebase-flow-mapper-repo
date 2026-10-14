# Mapping a backend / API / service repo

## What to establish
- **Boot sequence:** entry point → config load → DB/queue connections → middleware → routes. Find the file that wires it all.
- **Request path:** router → middleware (auth, validation, logging) → controller/handler → service/domain logic → repository/ORM → database.
- **Data model:** ORM models or schema files, migrations folder, which DB(s).
- **Async work:** queues, workers, cron/scheduled jobs, event consumers/producers (Kafka, RabbitMQ, SQS).
- **Integrations:** outbound HTTP clients, third-party SDKs, other internal services (look for base URLs in config).
- **API contract:** OpenAPI/proto/GraphQL schema files in the scan's `api_contract_files`. These are the most reliable description of the surface.
- **Auth and config:** how identity is established, which settings come from env (names only, never values).

## Diagrams to produce
- **L0:** clients → this service → datastores, queues, other services.
- **L1:** layered architecture with real package names; show where layering is violated if the import graph shows it (cycles).
- **L2 (pick 1-3):** *lifecycle of the most important request* as a `sequenceDiagram`; *a background job or event flow*; *deploy path* from CI to runtime.

## Where to look
Entry points, `routes/`, `controllers/`, `services/`, `models/`, `migrations/`, `docker-compose.yml` (reveals dependencies the service needs locally), CI files.

## Common traps
Dependency injection (Spring, NestJS, Django apps) hides wiring from the import graph; read module/config classes and mark those links inferred if you can't confirm.
