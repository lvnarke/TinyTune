# Eight-minute interview demonstration

For the current customer-facing account/sharing demo, start with
[`ACCESS_AND_SHARING.md`](ACCESS_AND_SHARING.md). The load lab is now on port 8081
and the read-only API reference on port 8082. All product requests, including k6
fixtures, are authenticated. The measurement discussion below describes the
original distributed-backend experiment, before mandatory access checks.

## 1. Product and topology — 60 seconds

Run `make demo`. Explain that playlist state is strongly consistent in PostgreSQL,
reads use a Redis projection, and plays are acknowledged after durable queueing but
become visible in statistics asynchronously.

## 2. Failure semantics — 90 seconds

Point to the consumer transaction and describe the crash-after-commit scenario.
The system uses at-least-once delivery plus an event ledger; it does not claim
exactly-once transport. Mention stale-message claiming, three retries, and the DLQ.

## 3. Observe normal operation — 60 seconds

Open Grafana, run `make smoke`, and show rate, p95, cache operations, worker rate,
and queue depth. Open JSON logs and correlate one request ID with its worker event.

## 4. Saturate and scale — 150 seconds

Run a shortened stepped test. With one 25 ms worker, queue depth should grow once
play arrival approaches its service rate. Scale to four workers, repeat, and show
the changed drain rate. Explain that worker scaling eventually meets the hot-row
or database limit.

```bash
STEP_RATES=50,100,200 STEP_DURATION_SECONDS=5 RUN_LABEL=demo make saturation
docker compose up -d --scale worker=4
STEP_RATES=50,100,200 STEP_DURATION_SECONDS=5 RUN_LABEL=demo-scaled make saturation
```

## 5. Before and after — 90 seconds

Contrast baseline synchronous updates/cache-off with async processing/cache-on.
The change moves analytics latency out of the admission path and reduces database
read pressure. It trades immediate statistics for bounded eventual consistency
and creates a backlog that must be operated.

## 6. Honest limitations — 60 seconds

Call out the single-node database/Redis, combined cache-and-queue Redis, AOF
durability window, cache race, lack of auth/TLS, missing outbox, and manual DLQ
replay. Close with the prioritized future-work list in the README.

The checked-in host result is a baseline saturation point of 600 target RPS and a
scaled saturation point of 2,200 target RPS. At the latter point, Nginx explicitly
reports that 512 worker connections are insufficient.

