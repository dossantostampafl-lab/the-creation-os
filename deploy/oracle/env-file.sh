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
  tmp="$(mktemp)"
  chmod 600 "$tmp"
  grep -vE "^$1=" .env > "$tmp" || true
  printf '%s=%s\n' "$1" "$2" >> "$tmp"
  cat "$tmp" > .env
  rm -f "$tmp"
}
