# Load testing and saturation

## Workload

The k6 runner creates a fresh playlist and track, then generates a constant arrival
rate per step:

- 70% playlist reads
- 30% play-event writes
- one intentionally hot playlist and track

This mix exercises cache efficiency, database validation, stream ingestion, worker
capacity, and hot-aggregate contention. It is a controlled stress scenario, not a
claim that real playlist traffic has this distribution.

## Saturation definition

An individual step violates the operating envelope when p95 latency exceeds 250
ms, failures exceed 1%, or achieved throughput is below 90% of the requested rate.
The reported saturation point is the first of two consecutive violating steps, or
a violating final step. This confirmation rule prevents a transient connection
spike from being treated as sustainable capacity. The report includes every step
so the knee can still be reviewed directly.

## Experiments

### Smoke

```bash
make smoke
```

### Baseline

```bash
make benchmark-baseline
```

Baseline changes two variables together—cache off and synchronous aggregation—to
show the original production risk quickly. For a scientific attribution test,
change only one variable at a time with Compose environment overrides.

### Optimized and scaled

```bash
make benchmark-scaled
```

## Interpretation

- Rising latency with flat errors indicates queueing before hard rejection.
- Database timeout counters indicate API-side pool saturation.
- Rising stream depth with healthy API latency indicates worker undercapacity.
- A queue that drains after the step is burst-tolerant; one that keeps growing is
  operating above sustainable worker throughput.
- More API replicas with no throughput gain indicates a shared dependency limit.
- More workers with no drain-rate gain suggests database or hot-row contention.

Use the generated result, the Grafana time window, and container resource usage
together. A client-side RPS number alone cannot identify what saturated.

The earlier Python asyncio runner remains available as `make python-load`, but k6
is authoritative. During verification, the Python generator itself consumed one
full CPU core above roughly 400 scheduled RPS and produced a false service limit.

