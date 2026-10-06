from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import threading
import uuid
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from jose import jwt

ISSUER = "https://auth.openai.com"
AUTHORIZE_URL = "https://auth.openai.com/api/accounts/authorize"
TOKEN_URL = "https://auth.openai.com/api/accounts/oauth/token"
JWKS_URL = "https://auth.openai.com/.well-known/jwks.json"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
DYNAMIC_CLIENT_ID = "dynamic_agent_client"
AGENT_NAME = "THE CREATION OS"


def _b64url_sha256(value: str) -> str:
    digest = hashlib.sha256(value.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _random_verifier() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(48)).decode("ascii").rstrip("=")


def _load_existing(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    return value if isinstance(value, dict) else {}


def _validate_id_token(id_token: str, *, client_id: str, nonce: str) -> dict[str, object]:
    with httpx.Client(timeout=15.0) as client:
        response = client.get(JWKS_URL)
        response.raise_for_status()
        jwks = response.json()
    header = jwt.get_unverified_header(id_token)
    keys = jwks.get("keys") if isinstance(jwks, dict) else None
    if not isinstance(keys, list):
        raise RuntimeError("OpenAI JWKS response did not contain keys")
    key = next(
        (
            item
            for item in keys
            if isinstance(item, dict) and item.get("kid") == header.get("kid")
        ),
        None,
    )
    if key is None:
        raise RuntimeError("OpenAI ID token signing key was not found")
    claims = jwt.decode(
        id_token,
        key,
        algorithms=[str(header.get("alg") or "RS256")],
        audience=client_id,
        issuer=ISSUER,
        options={"require_sub": True, "require_exp": True, "require_iat": True},
    )
    if claims.get("nonce") != nonce:
        raise RuntimeError("OpenAI ID token nonce did not match the authorization attempt")
    if not claims.get("sub"):
        raise RuntimeError("OpenAI ID token did not contain a subject")
    return dict(claims)


class _CallbackHandler(BaseHTTPRequestHandler):
    result: dict[str, str] | None = None
    event = threading.Event()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/auth/callback":
            self.send_response(404)
            self.end_headers()
            return
        query = parse_qs(parsed.query, keep_blank_values=True)
        type(self).result = {
            key: values[-1]
            for key, values in query.items()
            if values
        }
        type(self).event.set()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h2>ChatGPT connected.</h2>"
            b"<p>You can close this browser tab and return to THE CREATION OS.</p>"
            b"</body></html>"
        )

    def log_message(self, format: str, *args: object) -> None:
        return


def _save(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    os.chmod(path, 0o600)


def connect(*, output: Path, port: int, no_browser: bool, force_new: bool) -> None:
    existing = {} if force_new else _load_existing(output)
    saved_client_id = str(existing.get("client_id") or "").strip()
    client_id = saved_client_id or DYNAMIC_CLIENT_ID
    host_id = str(existing.get("ext_agent_host_id") or "").strip()
    if not host_id:
        host_id = "urn:uuid:" + str(uuid.uuid4())

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = _random_verifier()
    redirect_uri = f"http://127.0.0.1:{port}/auth/callback"

    params = {
        "client_id": client_id,
        "ext_agent_host_id": host_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "resource": RESOURCE,
        "state": state,
        "nonce": nonce,
        "code_challenge_method": "S256",
        "code_challenge": _b64url_sha256(verifier),
    }
    contains_id_token_hint = False
    if client_id == DYNAMIC_CLIENT_ID:
        params["agent_name_hint"] = AGENT_NAME
    else:
        retained_id_token = str(existing.get("id_token") or "").strip()
        email = str(existing.get("email") or "").strip()
        # id_token_hint is a credential-bearing hint: use it only when the URL is
        # opened directly by this process, never when the URL must be printed.
        if retained_id_token and not no_browser:
            params["id_token_hint"] = retained_id_token
            contains_id_token_hint = True
        if email:
            params["login_hint"] = email

    url = AUTHORIZE_URL + "?" + urlencode(params)

    _CallbackHandler.result = None
    _CallbackHandler.event.clear()
    server = ThreadingHTTPServer(("127.0.0.1", port), _CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if contains_id_token_hint:
            print(
                "Opening ChatGPT authorization in the browser. "
                "The authorization URL is intentionally not printed because it contains an ID-token hint."
            )
        else:
            print("Open this URL in the browser to connect ChatGPT:")
            print(url)
        if not no_browser:
            webbrowser.open(url)
        if not _CallbackHandler.event.wait(timeout=600):
            raise RuntimeError("Timed out waiting for the ChatGPT authorization callback")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    callback = _CallbackHandler.result or {}
    if callback.get("state") != state:
        raise RuntimeError("OAuth state did not match")
    if callback.get("error"):
        raise RuntimeError("ChatGPT authorization was not granted: " + callback["error"])
    code = callback.get("code")
    if not code:
        raise RuntimeError("ChatGPT authorization did not return a code")

    callback_client_id = callback.get("client_id")
    if client_id == DYNAMIC_CLIENT_ID:
        issued_client_id = str(callback_client_id or "").strip()
        if not issued_client_id or issued_client_id == DYNAMIC_CLIENT_ID:
            raise RuntimeError("Dynamic ChatGPT registration did not return an issued client_id")
    else:
        issued_client_id = client_id
        if callback_client_id and callback_client_id != issued_client_id:
            raise RuntimeError("ChatGPT callback returned a different client_id")

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": issued_client_id,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
                "resource": RESOURCE,
            },
        )
        if response.status_code >= 400:
            raise RuntimeError(f"ChatGPT token exchange failed with HTTP {response.status_code}")
        tokens = response.json()

    id_token = str(tokens.get("id_token") or "")
    access_token = str(tokens.get("access_token") or "")
    refresh_token = str(tokens.get("refresh_token") or "")
    scope = str(tokens.get("scope") or callback.get("scope") or "")
    scopes = {item for item in scope.split() if item}
    if not id_token or not access_token or not refresh_token:
        raise RuntimeError("ChatGPT token exchange returned incomplete credentials")
    if "chatgpt.tokens.use.direct" not in scopes:
        raise RuntimeError("ChatGPT plan usage permission was not granted")

    claims = _validate_id_token(id_token, client_id=issued_client_id, nonce=nonce)
    existing_subject = str(existing.get("subject") or "").strip()
    if existing_subject and str(claims.get("sub") or "") != existing_subject:
        raise RuntimeError(
            "ChatGPT reauthorization returned a different account identity; "
            "the saved registration was not replaced"
        )
    document: dict[str, object] = {
        "email": claims.get("email"),
        "issuer": ISSUER,
        "subject": claims["sub"],
        "client_id": issued_client_id,
        "ext_agent_host_id": host_id,
        "id_token": id_token,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": str(tokens.get("token_type") or "Bearer"),
        "expires_in": int(tokens.get("expires_in") or 3600),
        "scopes": sorted(scopes),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    _save(output, document)
    print(f"ChatGPT connection saved securely to: {output}")
    print("Plan usage permission: enabled")
    print("No token value was printed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect THE CREATION OS to a ChatGPT plan with OAuth.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("chatgpt-credentials.json"),
        help="Protected credential file to create or refresh.",
    )
    parser.add_argument("--port", type=int, default=1455)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--new",
        action="store_true",
        help="Register a new ChatGPT client instead of reusing the client in --output.",
    )
    args = parser.parse_args()
    connect(
        output=args.output.expanduser().resolve(),
        port=args.port,
        no_browser=args.no_browser,
        force_new=args.new,
    )


if __name__ == "__main__":
    main()
