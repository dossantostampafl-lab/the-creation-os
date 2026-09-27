#!/usr/bin/env bash
# Reading and writing the .env of a running installation. Sourced by install.sh and
# set-inference.sh; it assumes the caller is root and has cd'd to the repository root.
#
# A value is never passed through a sed expression. Any value holding the expression's
# delimiter would close the `s` command early, so sed aborts with "unknown option to `s'"
# and leaves .env untouched -- a silent no-op that reads as a successful run. An API key
# containing a '|' does exactly that. printf '%s' writes the value as literal text.

env_get() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }

env_set() {
  local tmp
  # .env is one variable per line, so a value carrying a newline does not merely truncate: the
  # text after it becomes another line, which Compose reads as another variable. Refusing here
  # covers every caller rather than trusting each one to check.
  if [[ "$2" == *$'\n'* || "$2" == *$'\r'* ]]; then
    echo "env_set: the value for $1 contains a line break, which would add a line to .env." >&2
    return 1
  fi
  tmp="$(mktemp)"
  chmod 600 "$tmp"
  grep -vE "^$1=" .env > "$tmp" || true
  printf '%s=%s\n' "$1" "$2" >> "$tmp"
  cat "$tmp" > .env
  rm -f "$tmp"
}
