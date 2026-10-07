# ChatGPT OAuth activation

THE CREATION OS uses OpenAI Sign in with ChatGPT for the `chatgpt` inference provider. No API key is required for this provider.

## What is already deployed by code

- Primary provider: `chatgpt`
- Default model: `gpt-6.1-sol`
- Fallback provider: `freellmapi`
- Credential path inside API/worker containers: `/var/lib/creation/chatgpt/credentials.json`
- Credentials are stored in the protected `chatgpt_credentials` Docker volume.
- Access tokens are refreshed using the rotating OAuth refresh token.

## One-time local authorization

OAuth must be completed on a computer that has the browser receiving the loopback callback.

From a fresh checkout of `main` on Linux/macOS:

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m app.inference.chatgpt_connect --output ../chatgpt-credentials.json
```

On Windows PowerShell:

```powershell
cd backend
py -3.12 -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -e .
.\\.venv\\Scripts\\python.exe -m app.inference.chatgpt_connect --output ..\\chatgpt-credentials.json
```

The command opens the official OpenAI authorization page, requests the ChatGPT plan-use permission, validates the returned ID token and writes a protected credential file. Do not commit, paste into chat, or log this file.

## Transfer to the self-hosted Oracle VM

Copy the credential file over a secure SSH channel to a temporary path on the VM, then from the repository root run:

```bash
sudo ./deploy/oracle/import-chatgpt-credentials.sh /tmp/chatgpt-credentials.json
rm -f /tmp/chatgpt-credentials.json
```

The import script preserves the VM's own stable host ID while installing the issued client registration and OAuth tokens into the shared protected volume.

## Verify end to end

In GitHub Actions, run the `Deploy` workflow with task:

```text
check-chatgpt-auth
```

A successful result ends with:

```text
AUTH_READY=yes
```

That task validates the credential structure and scope, refreshes the access token if needed, checks the account-visible model catalog, verifies `gpt-6.1-sol` is available, and performs one minimal Responses API inference. Token values are never printed.
