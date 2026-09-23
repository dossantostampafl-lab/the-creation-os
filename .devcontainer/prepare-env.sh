#!/bin/sh
# Prepare .env before the stack starts, so a Codespace boots ready to run.
#
# Three things, all idempotent and all safe to re-run:
#   1. Create .env from .env.example when it is missing.
#   2. Add settings the example has gained since this .env was written, keeping every
#      value already set by hand. An old .env is why a key can look configured and the
#      provider still answers nothing: the variable it needs simply is not in the file.
#   3. Fill blank secrets from the environment, so a Codespace secret is enough and the
#      key never has to be pasted into the editor — which the browser blocks on a tablet.
#
# It never overwrites a value that is already there and never prints a secret.
set -eu

cd "$(dirname "$0")/.."
[ -f .env.example ] || exit 0

if [ ! -f .env ]; then
  cp .env.example .env
  echo "prepare-env: created .env from .env.example"
fi
chmod 600 .env 2>/dev/null || true

# 2. Settings the example declares that this .env has never heard of.
added=0
for line in $(grep -E '^[A-Z][A-Z0-9_]*=' .env.example); do
  name=${line%%=*}
  if ! grep -qE "^${name}=" .env; then
    if [ "$added" -eq 0 ]; then
      printf '\n# Added by prepare-env from .env.example\n' >> .env
      added=1
    fi
    printf '%s\n' "$line" >> .env
    echo "prepare-env: added $name"
  fi
done

# 3. Secrets worth taking from the environment. Names only; values are never echoed.
fill() {
  name=$1
  # Only a blank line is filled, so anything set by hand wins.
  grep -qE "^${name}=$" .env || return 0
  [ -n "$(printenv "$name" 2>/dev/null || true)" ] || return 0
  awk -v key="$name" '
    $0 == key "=" { print key "=" ENVIRON[key]; next }
    { print }
  ' .env > .env.prepare-env.tmp && mv .env.prepare-env.tmp .env
  chmod 600 .env 2>/dev/null || true
  echo "prepare-env: filled $name from the environment"
}

for name in \
  ANTHROPIC_API_KEY ANTHROPIC_MODEL ANTHROPIC_BASE_URL \
  FREELLMAPI_API_KEY FREELLMAPI_MODEL FREELLMAPI_BASE_URL \
  OPENAI_COMPATIBLE_API_KEY OPENAI_COMPATIBLE_MODEL OPENAI_COMPATIBLE_BASE_URL \
  LLM_API_KEY LLM_MODEL LLM_FALLBACK_PROVIDERS \
  ELEVENLABS_API_KEY ELEVENLABS_VOICE_ID
do
  fill "$name"
done

# A provider whose credentials just arrived should be the one that answers: while
# LLM_PROVIDER is fake the system refuses to speak as DEUS rather than invent replies.
configured() { grep -qE "^$1=.+" .env; }
if grep -qE '^LLM_PROVIDER=fake$' .env; then
  chosen=
  if configured FREELLMAPI_API_KEY && configured FREELLMAPI_MODEL; then
    chosen=freellmapi
  elif configured ANTHROPIC_API_KEY && configured ANTHROPIC_MODEL; then
    chosen=anthropic
  fi
  if [ -n "$chosen" ]; then
    awk -v provider="$chosen" '
      $0 == "LLM_PROVIDER=fake" { print "LLM_PROVIDER=" provider; next }
      { print }
    ' .env > .env.prepare-env.tmp && mv .env.prepare-env.tmp .env
    chmod 600 .env 2>/dev/null || true
    echo "prepare-env: set LLM_PROVIDER=$chosen"
  fi
fi

if grep -qE '^LLM_PROVIDER=fake$' .env; then
  echo "prepare-env: no model configured — DEUS stays disabled until LLM_PROVIDER is set."
fi
