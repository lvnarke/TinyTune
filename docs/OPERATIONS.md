# Operations and failure injection

Current local tools: load lab `http://localhost:8081`, API reference
`http://localhost:8082/docs`, Grafana `http://localhost:3000`. None needs a customer
login. `/api/v1/ops/status` is served only on the load-lab listener; use port 8081
in the commands below. Customer product endpoints require a session and membership.

## Service objectives for the exercise

- API p95 below 250 ms while below the measured saturation point
- HTTP 5xx below 1%
- No duplicate aggregate updates for repeated event IDs
- Queue depth returns to zero after a bounded burst
- Readiness fails when a required durable dependency is unavailable

These are demonstration objectives, not claims based on production traffic.

## Signals

Use RED for the request path: rate, errors, and duration. Use saturation signals
for the internal resources: in-flight requests, database acquisition timeouts,
queue depth, and worker processing rate.

Useful commands:

```bash
docker compose ps
docker compose logs --tail=100 api worker gateway
curl -s http://localhost:8080/health/ready
curl -s http://localhost:8081/api/v1/ops/status
curl -s http://localhost:9090/api/v1/targets
```

## Failure drills

### Stop a worker

```bash
docker compose stop worker
make smoke
curl -s http://localhost:8081/api/v1/ops/status
docker compose start worker
```

Expected: play requests still return 202 while queue depth grows. After restart,
the worker drains the stream and statistics converge.

### Stop Redis

```bash
docker compose stop redis
curl -i http://localhost:8080/health/ready
docker compose start redis
```

Expected: readiness fails. Playlist cache reads fall back to PostgreSQL if the API
is still running, but asynchronous play acceptance returns 503 rather than claim
an event was accepted without persistence.

### Stop PostgreSQL

```bash
docker compose stop postgres
curl -i http://localhost:8080/health/ready
docker compose start postgres
```

Expected: readiness fails and durable operations cannot complete. Restart policies
may restart API/worker processes after dependency errors; inspect their JSON logs.

### Inspect or replay dead letters

```bash
docker compose exec redis redis-cli XRANGE tinytune:play-events:dlq - +
```

Replay is intentionally manual in this version. An operator must understand and
repair the failure before placing an event back on the primary stream.

## Alert candidates

- p95 above 250 ms for five minutes
- 5xx above 1% for five minutes
- database pool timeouts above zero
- queue depth increasing for five minutes, rather than merely nonzero
- worker failure or dead-letter count above zero
- readiness failure or missing Prometheus target

Alert on sustained or actionable conditions, not every transient backlog entry.

