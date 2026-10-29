# Customer accounts, private playlists and separate local tools

## Entry points

| Application | Local URL | Login |
|---|---|---|
| TinyTune customer app | http://localhost:8080 | Username/password; optional Google |
| Load lab | http://localhost:8081 | None, as requested |
| API reference | http://localhost:8082/docs | None; read-only |
| Grafana | http://localhost:3000 | Anonymous local viewer |
| Prometheus | http://localhost:9090 | Local operations endpoint |

All published ports bind to `127.0.0.1`. The customer navigation contains only
Your library, Shared with me, Favorites and the customer account menu. Operational
routes are not exposed on the customer listener. The load-lab listener blocks all
customer data and authentication routes, strips ambient cookies, and cannot be
used to view anyone's private library. The API-reference listener exposes only its
reference, schema and assets. Swagger assets are vendored locally and Try it out
is disabled, so browsing documentation does not execute customer operations.

The tools intentionally do not use customer accounts or operator login. They must
remain local; unauthenticated load execution is unsuitable for public hosting.

## Accounts

Create an account with a display name, unique username and a 12–128 character
password. Usernames are case-insensitive, 3–32 characters, start with a letter,
and contain letters, digits or underscores. Passwords are salted and hashed with
scrypt (`N=32768, r=8, p=3`); the raw password is never stored. These parameters
follow one of [OWASP's scrypt configurations](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
Sign-in throttles use shared Redis state. Sessions are opaque, seven-day HttpOnly,
SameSite=Lax cookies; Redis stores their hashed keys. They work across API replicas
and are invalidated on sign-out. The old anonymous demo bypass is disabled.

Google sign-in remains optional. Set `GOOGLE_CLIENT_ID` in `.env`, authorize
`http://localhost` and `http://localhost:8080` as JavaScript origins, then recreate
the API service. Google identities receive a stable username shown in the account
menu. No client secret is needed. Google requires internet; local accounts do not.
Never share by an unverified email address: sharing targets a specific existing
username/account. Local and Google identities are not automatically linked by email.

New accounts start with an empty library. All newly created playlists have an
owner and are private. The legacy sample-library initializer remains an explicit,
authenticated API operation for test/demo setup; the UI never creates samples
without asking. Old demo sessions are not accepted under the new session namespace.
Existing users and playlists are preserved. Legacy playlists with no owner are
inaccessible, rather than silently granted to arbitrary new accounts.

## Permissions

| Action | Owner | Editor | Viewer | Unrelated user |
|---|---|---|---|---|
| Read playlist and play statistics | Yes | Yes | Yes | No |
| Record a play | Yes | Yes | Yes | No |
| Add tracks | Yes | Yes | No | No |
| Favorite for oneself | Yes | Yes | Yes | No |
| List/change/revoke sharing | Yes | No | No | No |

An owner opens **Share playlist**, enters the recipient's registered username,
and chooses **Can view** or **Can edit**. The recipient sees the playlist in
**Shared with me**, alongside the owner's username and their own role. The owner
can change the role or remove access. Favorites belong to the person marking them;
favoriting a shared playlist does not alter the owner's favorites.

The copied URL is a locator, not a bearer credential. It only works for the owner
and explicitly authorized members. A logged-out visitor must sign in; an unrelated
account sees an invite-only message. The app does not send invitation emails.

Every product endpoint requires authentication, including old anonymous API paths.
Playlist reads check PostgreSQL membership **before** returning Redis-cached
content. Statistics, play ingestion, favorites and track writes also check access.
Unauthorized IDs return a generic 404 to avoid revealing playlist existence.
Insufficient permissions on a legitimately shared playlist return 403.

Membership writes and track appends lock the parent playlist row so revocation and
editing serialize. Requests authorized before a concurrent revocation can finish;
requests starting after it commits are denied. Cached content never caches a user's
permission. The browser clears a currently open playlist when its next three-second
poll observes revocation; already delivered data cannot be recalled from a client.

## Demo with Alice and Bob

1. Create Alice's account; create a playlist and add a track.
2. Create Bob's account in a separate browser profile/private window (or sign out
   of Alice before switching accounts). Tabs in one browser profile share a session.
3. Before sharing, Bob cannot open Alice's copied playlist URL.
4. As Alice, share the playlist with Bob's exact username as **Can view**.
5. Bob opens Shared with me: he can view/log plays but has no Add a track button.
6. Alice changes Bob to **Can edit**; Bob can then add a track.
7. Alice removes Bob. His next request is denied, even if the playlist was cached.
8. Open the load lab separately; it needs no customer account and cannot list
   customer playlists. Its k6 tests create isolated authenticated fixture accounts.

## Verification

`make verify-web` exercises real HTTP through three separate listeners and multiple
independent accounts. It checks registration, bad passwords, sign-out, sessions across
replicas, no anonymous bypass, private reads/counts/plays, viewer/editor rules,
owner-only sharing, per-user favorites, warmed-cache revocation, role downgrade,
header spoofing, tool isolation, real authenticated k6, progress, export and cancellation.

`make verify-google` tests Google account/session behavior with the verifier mocked;
interactive Google consent still needs the owner's registered client ID.

## Scope

TinyTune stores track metadata and counts plays; it does not stream audio. This
version does not implement email delivery/verification, password recovery, account
deletion, public playlists, playlist deletion, track removal/reordering or ownership
transfer. Before public deployment: add HTTPS/Secure cookies, recovery and abuse
controls, and protect the local operations tools with network isolation and access
controls appropriate to the deployment.

The original 600/2,200 RPS measurements predate mandatory authentication and ACL
checks. Re-run load tests for the current build; the new checks deliberately add
database and Redis work to preserve private access.
