# Local Docker secrets

Create these files before starting the Compose stack:

- `app_secret_key.txt`
- `creator_bootstrap_password.txt`
- `database_url.txt`
- `postgres_password.txt`
- `worker_credential.txt`
- `elevenlabs_api_key.txt` (may be empty when disabled)
- `github_token.txt` (may be empty)
- `llm_api_key.txt` (may be empty)

Run `./scripts/generate-secrets.ps1` to create all of these with random values
in one step (safe to re-run; existing non-empty files are left untouched
unless `-Force` is passed).

The directory contents are ignored by Git. In production, provision the same
secret names from your deployment platform or external secret manager rather
than storing secret files in the repository checkout.

`database_url.txt` must contain the complete SQLAlchemy URL and use the same
PostgreSQL password as `postgres_password.txt`.

`worker_credential.txt` is the plaintext bearer credential the `worker`
service authenticates with; the API's startup bootstrap
(`app.admin.worker.restore_configured_worker`) stores only its SHA-256 hash
in the database. Never registered through a public endpoint.
