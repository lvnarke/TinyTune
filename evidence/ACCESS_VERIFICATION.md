# Customer access verification — October 29, 2026

The local integration suite passed against three API replicas and four workers.
It used four independent registered accounts plus an anonymous client and the
separate unauthenticated local tools listener.

- Local registration and returning login; incorrect-password rejection.
- Case-insensitive usernames, duplicate rejection and password length validation.
- Shared sessions across API replicas and session invalidation on logout.
- Anonymous demo bypass disabled; foreign-Origin writes rejected.
- Unauthenticated playlist reads/writes rejected with 401.
- Unrelated users denied private content, statistics, plays and sharing with 404.
- Owner, editor and viewer capabilities enforced by the server.
- Only owners can list, grant, downgrade or revoke access.
- Viewer can read/log plays but cannot append tracks.
- Editor can append tracks but cannot manage access.
- Favorites are per-user, including favorites on shared playlists.
- Revocation denied the next read even after warming the Redis content cache.
- Revoked users cannot read counts, log plays or favorite the old playlist.
- Editor-to-viewer downgrade immediately denied subsequent track mutations.
- Customer listener cannot be turned into the tools listener by header spoofing.
- Load lab exposes no customer library/authentication routes.
- API reference loads on port 8082 and exposes no customer data routes.
- Real k6 execution creates a private fixture account; both 10/20 RPS stages had
  zero client errors, with live samples and downloadable results.
- Single experiment admission, cancellation and runner metrics passed.

Google account creation, returning identity, expected audience, nonce replay,
wrong nonce, verifier rejection and unverified-email rejection passed with Google's
external verifier mocked. Interactive Google login still needs a client ID.

Reproduce with `make verify-web` and `make verify-google`. Tests create isolated
accounts/playlists and do not delete or reset existing data. The original anonymous
test script was replaced with `scripts/verify_permissions.py`.
