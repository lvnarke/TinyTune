# TinyTune frontend — current v1.2

The current feature and permission guide is [Accounts and sharing](ACCESS_AND_SHARING.md).

- Customer app: **http://localhost:8080**. Create a local username/password account,
  create private playlists, add tracks, and grant named recipients viewer/editor access.
- Local load dashboard: **http://localhost:8081**, no login. Uses real k6 with isolated
  authenticated fixtures, live metrics, charts, cancellation and report downloads.
- Read-only API reference: **http://localhost:8082/docs**, no login.
- Grafana: **http://localhost:3000**, anonymous local viewer.

Customer navigation never links to tools. The customer app no longer has an
anonymous demo-login bypass or public playlist-by-ID access. A copied link alone
does not grant access. New accounts start empty; only owned and explicitly shared
playlists appear in the library.

Run `docker compose up --build -d` to start. No Node.js build server is needed;
UI assets, original cover art, fonts, charts and API-reference assets are local.
Google Identity Services is an optional external dependency for Google sign-in.

## Google configuration

1. Create a Web application OAuth client in Google Cloud Console.
2. Authorize `http://localhost` and `http://localhost:8080` as JavaScript origins.
3. Set `GOOGLE_CLIENT_ID` in `.env`. No client secret is required.
4. Run `docker compose up -d --force-recreate api`, then refresh the customer app.

The server verifies Google's signature/issuer/audience/expiration and a one-time
nonce, then establishes the same shared session used by local accounts. Google
identities get a stable username shown in the account menu. Interactive Google
consent remains unverified until the owner's registered client ID is supplied.
Local accounts need no Google configuration or internet connection.

## Verification

Run `make verify-web` for real multi-account authorization and k6 integration checks,
and `make verify-google` for Google identity/session tests with the external verifier
mocked. See [verification evidence](../evidence/ACCESS_VERIFICATION.md).

TinyTune manages track metadata and play events; it does not stream audio. Sharing
targets registered usernames and does not send email. Password recovery is not yet
implemented. All unauthenticated operations tools must remain local.
