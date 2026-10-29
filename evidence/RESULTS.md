# Verified results

These are historical measurements of the original distributed backend, before the
web/authentication extension. They remain experiment evidence, not a capacity claim
for the updated version. Use the Load lab or CLI to measure the current build.

These measurements were captured on October 29, 2026 using Docker Desktop with 8
CPUs and 7.7 GiB assigned memory. k6 generated constant arrival rates against a
fresh hot playlist using a 70/30 read/play mix. Exact capacity is host-specific;
the workload, thresholds, and reports are reproducible from the repository.

## Authoritative result

| Configuration | Last healthy tested rate | Confirmed saturation point |
|---|---:|---:|
| Baseline: one API, one worker, cache off, synchronous plays | 400 RPS | 600 RPS |
| Improved: three APIs, four workers, cache on, async plays | 2,000 RPS | 2,200 RPS |

The changes raised the last healthy tested rate from 400 to 2,000 RPS (5x) and the
confirmed saturation onset from 600 to 2,200 target RPS (3.67x).

## Baseline k6 curve

| Target RPS | Achieved RPS | p50 ms | p95 ms | p99 ms | Errors | Violates envelope |
|---:|---:|---:|---:|---:|---:|:---:|
| 50 | 50.0 | 2.90 | 51.16 | 237.51 | 0% | no |
| 100 | 100.0 | 2.83 | 6.33 | 8.67 | 0% | no |
| 200 | 199.8 | 2.45 | 5.63 | 8.38 | 0% | no |
| 400 | 399.6 | 2.25 | 6.91 | 8.44 | 0% | no |
| 600 | 500.0 | 30.27 | 1,045.39 | 1,579.10 | 21.96% | yes |
| 800 | 712.6 | 10.76 | 1,293.82 | 1,562.61 | 61.66% | yes |

At 600 target RPS, the synchronous hot-row path increases concurrency until Nginx
hits its connection ceiling. Throughput falls below 90% of target, p95 exceeds one
second, and 21.96% of requests fail.

## Improved and scaled sustained curve

| Target RPS | Achieved RPS | p50 ms | p95 ms | p99 ms | Errors | Violates envelope |
|---:|---:|---:|---:|---:|---:|:---:|
| 1,600 | 1,599.2 | 1.98 | 21.38 | 128.99 | 0% | no |
| 1,800 | 1,799.7 | 2.11 | 7.60 | 18.27 | 0% | no |
| 2,000 | 1,999.6 | 3.33 | 33.59 | 88.38 | 0% | no |
| 2,200 | 2,182.4 | 30.67 | 179.87 | 473.45 | 3.67% | yes |
| 2,400 | 2,376.3 | 21.21 | 234.58 | 1,140.13 | 14.29% | yes |

At 2,200 target RPS, the error rate is the first confirmed threshold violation.
Nginx logs explicitly report `512 worker_connections are not enough`; the gateway
resets connections while API p95 remains below the 250 ms limit. This is the first
hard limiter in the final tested configuration.

## Worker scaling and backpressure

The high-rate run left 19,895 accepted play events in Redis Streams. That backlog
is deliberate evidence that decoupling protects admission latency but does not
create downstream capacity.

- Four workers drained at approximately 133 events/second.
- Eight workers drained 2,799 events in ten seconds, approximately 279 events/second.
- The measured drain rate improved about 2.1x when worker count doubled.

Beyond that point, more workers will eventually stop helping because all events for
the hot test track update one PostgreSQL aggregate row.

## Delivery-failure verification

A malformed event was inserted into the primary stream. The worker retried it
three times, then acknowledged it from the primary stream and wrote it to
`tinytune:play-events:dlq` with the original message ID and failure text. The
observed error was `badly formed hexadecimal UUID string`.

## Load-generator validation

An initial Python asyncio runner became CPU-bound at one core above roughly 400
scheduled RPS and produced a false service limit. Those exploratory reports remain
in `results/` for transparency but are not authoritative. The final measurements
use containerized k6, constant-arrival-rate execution, rate-dependent warm-up, and
ten-second boundary stages. The saturation point requires two consecutive envelope
violations, preventing a single transient connection spike from defining capacity.

## Authoritative report files

- `results/20261029T222159Z-baseline-k6-k6.json` and `.md`
- `results/20261029T222321Z-optimized-scaled-k6-k6.json` and `.md`
- `results/20261029T223115Z-optimized-scaled-sustained-k6-k6.json` and `.md`

