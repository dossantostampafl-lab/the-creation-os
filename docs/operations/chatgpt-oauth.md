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
- Automatic billing fallback from ChatGPT: **disabled by design**. A ChatGPT-plan failure stops that request; the UI surfaces the plan/usage state instead of silently switching providers.
- Credential path inside API/worker containers: `/var/lib/creation/chatgpt/credentials.json`
- API and worker share the protected `chatgpt_credentials` Docker volume.

## One-time authorization for the Oracle host

OpenAI binds this flow to a stable `ext_agent_host_id`. The Oracle runtime must therefore know its host ID **before** the browser authorization is created. Do not authorize on one host and then relabel the credential file for another host.

First deploy the stack on Oracle, then from the repository root on the VM run:

```bash
sudo bash ./deploy/oracle/chatgpt-host-id.sh
```

Copy the printed `urn:uuid:...` value. It is an opaque host identifier, not a bearer token.

On the computer that will run the browser callback, create a dedicated Oracle profile using that exact host ID. From a fresh checkout of `main` on Linux/macOS:

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m app.inference.chatgpt_connect --new --profile oracle --host-id 'urn:uuid:ORACLE_HOST_ID'
```

On Windows PowerShell:

```powershell
cd backend
py -3.12 -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -e .
.\\.venv\\Scripts\\python.exe -m app.inference.chatgpt_connect --new --profile oracle --host-id 'urn:uuid:ORACLE_HOST_ID'
```

The profile is written outside the checkout:

- Linux/macOS: `~/.config/the-creation-os/chatgpt/profiles/oracle/credentials.json`
- Windows: `%USERPROFILE%\\.config\\the-creation-os\\chatgpt\\profiles\\oracle\\credentials.json`

Use another profile name for another ChatGPT account/workspace registration. If plan-use consent was previously declined for the same Oracle registration, rerun the selected profile with `--enable-plan`; the helper reuses the issued client, the same Oracle host ID, and the retained account hints. Never paste token values into chat, logs, source control, analytics, or support transcripts.

## Transfer to the self-hosted Oracle VM

Copy the Oracle-bound profile's `credentials.json` over SSH to a temporary VM path, then from the repository root run:

```bash
sudo bash ./deploy/oracle/import-chatgpt-credentials.sh /tmp/chatgpt-credentials.json
rm -f /tmp/chatgpt-credentials.json
```

The importer refuses a partial installation unless API and worker share the same persistent credential volume. It also refuses credentials whose saved `ext_agent_host_id` differs from the Oracle host ID; it never rewrites host identity after OAuth.

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

If authentication has not been completed yet, the deployed stack must report ChatGPT unavailable and stop ChatGPT-plan inference. It must not silently switch the same request to another billing path.


## Account profiles and sign-out

Each ChatGPT account/workspace registration has its own protected profile. List local registrations without printing credentials:

```bash
manage-chatgpt list
```

Sign out one profile:

```bash
manage-chatgpt sign-out --profile default
```

Sign-out discovers OpenAI's current OIDC revocation endpoint and attempts refresh-token revocation. HTTP 200 is treated as confirmed revocation. Network/5xx failures use bounded retry. Local bearer credentials are cleared even if remote revocation cannot be confirmed, while the issued client/account/host mapping is retained so reauthorization remains stable. If remote revocation was not confirmed, disconnect the app from ChatGPT settings as well.

## Runtime failure semantics

A ChatGPT-plan request never silently crosses to FreeLLMAPI, Anthropic, OpenAI API billing, or another provider. The SIWC error code, upstream HTTP status, request ID, parameter, and parsed upstream error payload are preserved internally; only safe structured fields are returned to the Creator UI. Temporary plan-availability failures receive bounded retry. Usage-limit, authorization-context, eligibility, unsupported-capability, and unsupported-route failures do not loop OAuth or retry the same invalid request.

The composer shows **Using ChatGPT plan**, the active account label when OpenAI supplied one, and a **Manage usage** action. On the first healthy plan connection the UI shows a one-time welcome explaining that ChatGPT-plan usage is separate from API billing.

## Background and automation consent

Sign in with ChatGPT permits background/automation use only with explicit user consent. THE CREATION OS keeps autonomous discovery/competition disabled by default, and Mission execution remains Creator-authorized. Enabling autonomous profiles is therefore an explicit operational opt-in; deployments intended for another user must obtain that user's consent before enabling ChatGPT-backed background work.
