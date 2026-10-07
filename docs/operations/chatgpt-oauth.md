# ChatGPT OAuth activation

THE CREATION OS uses OpenAI **Sign in with ChatGPT** for the `chatgpt` inference provider. This path uses the user's eligible ChatGPT plan and OAuth credentials; it does **not** require an OpenAI API key.

## OpenAI contract implemented here

The implementation follows the OpenAI open-source/self-hosted VM flow:

- initial registration uses `client_id=dynamic_agent_client`, a stable per-host `ext_agent_host_id`, and `agent_name_hint=THE CREATION OS`;
- each authorization attempt uses fresh `state`, OIDC `nonce`, and PKCE S256;
- the callback is exactly `http://127.0.0.1:<port>/auth/callback`;
- requested scopes are `openid profile email offline_access resource.invoke chatgpt.tokens.use.direct`;
- the resource is `https://api.openai.com/v1`;
- the issued `client_id` is persisted before the code exchange so an `invalid_grant` retry reuses the issued registration;
- ID tokens are verified against OpenAI JWKS with issuer, audience, expiry, nonce, and subject checks;
- the token response, not the browser callback, is authoritative for granted scopes;
- access/refresh/ID tokens are stored outside source control with atomic owner-only writes;
- refreshes are serialized across API/worker processes because refresh tokens rotate;
- terminal refresh-token errors clear unusable tokens while retaining the issued client/account/host mapping for reauthorization;
- inference uses only the public `POST https://api.openai.com/v1/responses` route with `store=false`, `stream=true`, array input, and completion only after `response.completed`;
- model discovery uses `GET /v1/models` and display-visible model slugs;
- structured ChatGPT-plan usage/authentication errors are mapped to fallback, reauthorization, or non-success paths instead of being treated as successful inference.

## Runtime deployed by code

- Primary provider: `chatgpt`
- Default model: `gpt-6.1-sol`
- Fallback provider: `freellmapi`
- Credential path inside API/worker containers: `/var/lib/creation/chatgpt/credentials.json`
- API and worker share the protected `chatgpt_credentials` Docker volume.

## One-time local authorization

OpenAI's loopback callback reaches the computer running the browser, not the remote Oracle VM. Complete OAuth locally, then transfer the selected protected profile to the VM.

From a fresh checkout of `main` on Linux/macOS:

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m app.inference.chatgpt_connect
```

On Windows PowerShell:

```powershell
cd backend
py -3.12 -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -e .
.\\.venv\\Scripts\\python.exe -m app.inference.chatgpt_connect
```

The default profile is written outside the checkout at:

- Linux/macOS: `~/.config/the-creation-os/chatgpt/profiles/default/credentials.json`
- Windows: `%USERPROFILE%\\.config\\the-creation-os\\chatgpt\\profiles\\default\\credentials.json`

Use `--profile NAME` for another ChatGPT account/workspace registration. A stable host ID is kept separately under the ChatGPT config root. If plan-use consent was previously declined, rerun the selected profile with `--enable-plan`; the helper reuses the issued client and requests consent again. Never paste token values into chat, logs, source control, analytics, or support transcripts.

## Transfer to the self-hosted Oracle VM

Copy the selected profile's `credentials.json` over SSH to a temporary VM path, then from the repository root run:

```bash
sudo ./deploy/oracle/import-chatgpt-credentials.sh /tmp/chatgpt-credentials.json
rm -f /tmp/chatgpt-credentials.json
```

The importer refuses a partial installation unless API and worker share the same persistent credential volume. It preserves the VM's own stable host ID while installing the issued client registration and token set.

## Verify end to end

In GitHub Actions, run the `Deploy` workflow task:

```text
check-chatgpt-auth
```

A successful full check ends with:

```text
AUTH_READY=yes
```

The check validates the protected credential record, refreshes the access token when needed, fetches the account-specific model catalog, verifies that the configured model appears in the display-visible catalog, and performs one minimal Responses API inference. The catalog alone is not treated as entitlement proof; the completed inference is the final proof.

If authentication has not been completed yet, the deployed stack may correctly report ChatGPT unavailable and use FreeLLMAPI as reserve. That is an expected pre-authentication state, not a successful OAuth proof.
