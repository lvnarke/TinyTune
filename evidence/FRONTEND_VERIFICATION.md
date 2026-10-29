# Web extension verification — October 29, 2026

> Historical v1.1 verification. The customer authentication and sharing model has
> since changed. Current behavior and tests are documented in
> `docs/ACCESS_AND_SHARING.md` and `evidence/ACCESS_VERIFICATION.md`.

The app and load lab were exercised in the local browser against three API replicas,
four workers, PostgreSQL, Redis and the separate k6 runner.

## Browser verification

- Local demo login initializes a real personal library.
- Created **Interview mixtape**, added **Eventually Consistent / The Replicas**,
  and recorded a play. The asynchronously updated count became one.
- Launched **Interview · 50 to 200 RPS** from the load lab.
- The client chart received live samples. The final k6 report showed:

| Target RPS | Achieved RPS | p95 | Errors |
|---:|---:|---:|---:|
| 50 | 50 | 4.9 ms | 0% |
| 100 | 100 | 4.9 ms | 0% |
| 200 | 200 | 4.6 ms | 0% |

Report: `results/ui-d3a09a59-de64-4f1d-bd70-d151dd1944c5.json`.
These are smoke-test observations, not a saturation or sustainable-capacity claim.

- Verified responsive load-lab layout at 390 px: document width equaled viewport
  width, without horizontal overflow. Desktop preview was restored afterward.
- The console correctly reports three APIs and four workers. Replica queries
  exclude old scrape samples left over after process replacement or scaling.

An earlier browser experiment overlapped a deployment and observed HTTP failures.
Its report is intentionally retained in the notebook. The later run above used
the stable updated stack and completed inside the operating envelope.

## Automated integration checks

`make verify-web` exercises real HTTP, shared sessions across replicas, cookie
flags, foreign-Origin rejection, owner isolation, idempotent library initialization,
public sharing, favorite authorization, effectively-once play aggregation, invalid
load settings, single-run admission, real k6 execution, live progress, report download,
cross-user job isolation, cancellation, live metrics and session invalidation.

`make verify-google` uses the real local database and Redis with Google's token
verifier mocked. It covers first account creation, returning user identity,
expected audience delegation, one-time nonce rejection, invalid-signature failure,
nonce mismatch and unverified email rejection.

## Remaining external configuration

No real Google OAuth client ID was available. Interactive Google account consent
and login were **not** verified. The implementation uses Google's official verifier;
the UI explicitly shows setup instructions and offers a separate demo login.
See `docs/FRONTEND.md` to configure the client ID and authorized origins.
