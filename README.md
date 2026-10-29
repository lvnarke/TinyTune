# TinyTune

> **Current v1.2:** customer login is required; playlists are private with
> owner/editor/viewer sharing. Local dashboards have no login and live on separate
> ports. See [accounts, permissions and the current demo](docs/ACCESS_AND_SHARING.md).
> Older benchmark evidence describes the earlier backend configuration.

TinyTune is a small, production-shaped distributed system that runs entirely on a
local machine. Users create and share playlists; play events are accepted by a
stateless API and processed asynchronously by horizontally scalable workers.

The project is intentionally narrow in product scope so its distributed-systems
behavior is easy to run, observe, overload, and explain.

## Web app and load lab

Open **http://localhost:8080** for the responsive playlist frontend. Create and share
playlists, add tracks, save favorites, search your library and record listening events.
**http://localhost:8081** runs real k6 experiments with live throughput,
queue depth, service metrics, cancellation, history and downloadable reports.

Local username/password sign-up and sign-in work without external configuration.
Google is an optional additional provider: supply `GOOGLE_CLIENT_ID` in `.env` and
authorize the localhost origin in Google Cloud. No client secret is needed. The
anonymous demo bypass is removed. See [accounts and sharing](docs/ACCESS_AND_SHARING.md)
for exact instructions, permissions, local tool boundaries and verification.
The app records play events; it does not stream audio.

## What it demonstrates

- Stateless API replication behind a load balancer
- PostgreSQL as the durable source of truth
- Cache-aside reads with mutation invalidation and bounded TTL
- Redis Streams consumer groups and at-least-once processing
- Idempotent consumers, stale-message claiming, retries, and a dead-letter stream
- Eventual consistency between event acceptance and analytics reads
- Backpressure through visible queue growth
- Bounded database pools and explicit overload responses
- Prometheus RED metrics, structured JSON logs, request correlation, and Grafana
- A repeatable stepped load test that calculates the service's saturation point
- Runtime switches for a synchronous baseline and an improved asynchronous design

## Start locally

Requirements: Docker Desktop with Docker Compose. No host Python, database, Redis,
or load-test tool is required.

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
make demo
```

The first start pulls the pinned container images and can take a few minutes.

| Surface | URL |
|---|---|
| Playlist app | <http://localhost:8080> |
| Load lab (no login) | <http://localhost:8081> |
| API reference (no login, read-only) | <http://localhost:8082/docs> |
| Grafana TinyTune dashboard | <http://localhost:3000/d/tinytune-system/tinytune-system> |
| Prometheus | <http://localhost:9090> |
| Readiness | <http://localhost:8080/health/ready> |

Grafana is provisioned for anonymous local viewing; no password is needed. Customer
accounts have no operator role. All tools remain loopback-only and are separate
from the customer app.

## API

| Method | Path | Semantics |
|---|---|---|
| `POST` | `/api/v1/playlists` | Durable playlist creation |
| `POST` | `/api/v1/playlists/{id}/tracks` | Transactional track append and cache invalidation |
| `GET` | `/api/v1/playlists/{id}` | Cache-aside playlist read |
| `POST` | `/api/v1/playlists/{id}/plays` | Idempotent play acceptance; async by default |
| `GET` | `/api/v1/playlists/{id}/stats` | Eventually consistent play counts |
| `GET` | `/api/v1/ops/status` | Demo-facing configuration and queue status |

`Idempotency-Key` is supported on the play endpoint. Repeated delivery may enqueue
the same logical event more than once, but the worker's `processed_events` insert
and aggregate update share one database transaction, so the count changes once.

All playlist endpoints now require a session and a playlist-specific permission.
Reads, statistics and play recording require owner/editor/viewer access; track
append requires owner/editor. Only owners can manage `/playlists/{id}/sharing`.
Keys are scoped by account, playlist and track. CLI demos and k6 register isolated
fixture accounts instead of bypassing the authorization checks.

## Observe it

Open the Grafana dashboard, run `make smoke`, and watch:

- Request rate and p50/p95/p99 latency
- 5xx error rate and in-flight requests
- Cache hits, misses, writes, and invalidations
- Redis Stream queue depth
- Worker throughput, failures, and dead letters
- Database connection-pool timeouts

Every API and worker log is JSON. Normal successful operations are deterministically
sampled at 1%; slow requests, 5xx responses, duplicate events, retries, and dead
letters are always logged. Request IDs flow from Nginx to the API and into queued
events, allowing an accepted play to be correlated with its worker result:

```bash
docker compose logs -f gateway api worker
```

Prometheus uses DNS service discovery, so scaled API and worker replicas are
scraped individually rather than collapsing to a single container.

## Measure saturation

The authoritative load runner is containerized k6 using constant-arrival-rate
scenarios and a 70/30 mix of cached playlist reads and play-event writes. It
increases target arrival rate and writes JSON and Markdown reports to `results/`.
A Python runner remains available as `make python-load` for lightweight debugging,
but it is not used for the final saturation result because its own single-core
CPU limit can become the bottleneck.

```bash
make saturation
```

`make saturation` is a quick default ladder. The two fully reproducible comparison
runs used for the checked-in evidence are:

```bash
make benchmark-baseline
make benchmark-scaled
```

An individual step violates its operating envelope when any of these occurs:

1. p95 latency exceeds 250 ms;
2. errors exceed 1%; or
3. achieved throughput falls below 90% of target throughput.

The reported saturation point is the first of two consecutive violating steps (or
a violating final step). Requiring confirmation prevents one transient connection
spike from being misreported as sustainable capacity.

Override the rates or duration without changing code:

```bash
STEP_RATES=25,50,100,200,400,800 STEP_DURATION_SECONDS=15 \
RUN_LABEL=single-api-single-worker docker compose --profile load run --rm --no-deps k6
```

### Baseline and improvement experiment

The baseline performs play-count updates synchronously and disables the playlist
cache. All play requests for the test playlist contend on one aggregate row.

```bash
make baseline
STEP_RATES=50,100,200,400,600,800 STEP_DURATION_SECONDS=5 \
RUN_LABEL=baseline make saturation
```

The optimized design restores cache-aside reads and decouples play aggregation:

```bash
make optimized
docker compose up -d --scale api=3 --scale worker=4
STEP_RATES=1600,1800,2000,2200,2400 STEP_DURATION_SECONDS=10 \
RUN_LABEL=optimized-scaled make saturation
```

Compare the two Markdown reports in `results/`. Do not claim a universal RPS
number: the saturation point depends on the host. The checked-in runner makes the
measurement and definition reproducible.

On the verified Docker Desktop host, the baseline saturated at 600 target RPS. The
scaled design stayed healthy through 2,000 RPS and saturated at 2,200 when Nginx's
512-worker-connection ceiling began resetting connections. See
[`evidence/RESULTS.md`](evidence/RESULTS.md) for the complete curves.

## Scaling behavior

```bash
docker compose up -d --scale api=3
docker compose up -d --scale worker=4
```

- API replicas increase admission and cached-read capacity. Nginx resolves the
  Compose service name dynamically across replicas and pools upstream keepalive
  connections to avoid socket churn under repeated tests.
- Worker replicas share the Redis consumer group. Scaling workers increases drain
  rate until PostgreSQL row contention or database capacity becomes the limiter.
- The default 25 ms worker delay models downstream enrichment and makes
  backpressure visible on a laptop: one worker is limited to roughly 40 events/s
  before database overhead, while four can process independent events in parallel.

## Expected failure modes

| Pressure or failure | Observable behavior | Current response |
|---|---|---|
| Database pool saturation | p95 and `db_pool_timeouts_total` rise; API returns 503 | One-second bounded acquisition prevents unbounded request buildup |
| Play rate exceeds worker service rate | Redis Stream depth grows | API remains responsive; scale workers or shed load at a queue threshold |
| Hot playlist in synchronous mode | Row-lock waits serialize updates | Async mode removes that work from request latency |
| Gateway connection saturation | Nginx reports `worker_connections are not enough` and resets connections | Keepalive delays the limit; tune/scale the gateway or shed load |
| Worker dies after DB commit, before ACK | Event is reclaimed and delivered again | Unique event ID makes replay a no-op |
| Poison or repeatedly failing event | Failure count rises; message would loop | Third failure moves it to `tinytune:play-events:dlq` |
| Redis unavailable | Cached reads fall back to Postgres; async plays return 503 | No false acceptance when the queue cannot persist the event |
| PostgreSQL unavailable | Readiness fails; durable operations return failure | Load balancer has a readiness signal; no in-memory source-of-truth fallback |
| Cache invalidation race | A stale value may live for up to 30 seconds | Mutation invalidation plus TTL bounds staleness |

Redis AOF is configured with `appendfsync everysec`, so a host crash can lose up to
roughly one second of accepted stream writes. That explicit durability/latency
tradeoff would need revisiting for payments or another loss-intolerant domain.

## Stop or reset

```bash
docker compose down                  # retain local data
docker compose down -v               # remove TinyTune volumes and all local data
```

## Share the code

```bash
make package
```

This produces `../tinytune-distributed-system.zip` without local credentials,
generated results, or Python cache files.

## Documentation

- [Architecture and consistency decisions](docs/ARCHITECTURE.md)
- [Operations and failure injection](docs/OPERATIONS.md)
- [Load testing and result interpretation](docs/LOAD_TESTING.md)
- [Eight-minute interview demonstration](docs/DEMO.md)
- [Verified k6 results](evidence/RESULTS.md)

## With more time

- Use a transactional outbox and CDC instead of accepting events directly into
  Redis Streams when lossless publication is a requirement.
- Separate cache and queue Redis deployments to remove a shared failure domain.
- Add authentication, authorization, per-tenant quotas, and abuse controls.
- Use PostgreSQL HA, Redis replication, TLS, secret management, and backups.
- Add OpenTelemetry traces and exemplars linking p95 metrics to request traces.
- Add cache request coalescing to prevent a stampede on hot-key expiry.
- Partition play aggregates and batch database updates to reduce hot-row locking.
- Add automated DLQ inspection/replay, retention policies, and event schema versions.
- Run fault, soak, and recovery tests in CI on multiple machine profiles.

