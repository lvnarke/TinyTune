"""Exercise Google account/session behavior with the external verifier mocked.

Uses the real local database and Redis. This does not claim an interactive Google
login was tested; that requires the owner's registered client ID and consent.
"""

import os
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from app.main import app

headers = {"X-TinyTune-Request": "1"}
subject = f"test-google-{uuid4()}"
with patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "test-client.apps.googleusercontent.com"}):
    with TestClient(app, headers=headers) as client:
        config = client.get("/auth/config").json()
        claims = {"sub": subject, "email": "integration@example.test", "email_verified": True,
                  "name": "Google Test Listener", "nonce": config["nonce"]}
        with patch("app.web.id_token.verify_oauth2_token", return_value=claims) as verify:
            first = client.post("/auth/google", json={"credential": "test-credential-never-a-real-token"})
            assert first.status_code == 200, first.text
            first_id = first.json()["user"]["id"]
            assert verify.call_args.args[2] == "test-client.apps.googleusercontent.com"
            replay = client.post("/auth/google", json={"credential": "test-credential-never-a-real-token"})
            assert replay.status_code == 401
            client.post("/auth/logout")
            config = client.get("/auth/config").json()
            claims["nonce"] = config["nonce"]
            second = client.post("/auth/google", json={"credential": "test-credential-never-a-real-token"})
            assert second.status_code == 200, second.text
            assert second.json()["user"]["id"] == first_id
        config = client.get("/auth/config").json()
        with patch("app.web.id_token.verify_oauth2_token", side_effect=ValueError("Invalid signature")):
            assert client.post("/auth/google", json={"credential": "invalid-credential"}).status_code == 401
        with patch("app.web.id_token.verify_oauth2_token", return_value={**claims, "nonce": "wrong-nonce"}):
            assert client.post("/auth/google", json={"credential": "invalid-credential"}).status_code == 401
        with patch("app.web.id_token.verify_oauth2_token", return_value={**claims, "nonce": config["nonce"], "email_verified": False}):
            assert client.post("/auth/google", json={"credential": "invalid-credential"}).status_code == 401
print("PASS: Google first sign-up, returning sign-in, audience delegation, nonce replay, invalid signature, wrong nonce, unverified email")
