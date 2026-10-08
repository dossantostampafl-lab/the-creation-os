#!/usr/bin/env bash
# Keeps the sites other projects on this server add to deploy/Caddyfile.
#
# Another project that shares this Caddy (Star Trek 1, for one) appends its own site to
# deploy/Caddyfile between two marker lines:
#
#   # >>> name ...
#   ...its site...
#   # <<< name
#
# That file is tracked here, so updating it from the repository would wipe those blocks, and a
# fast-forward refuses to run at all while the file carries them. This script brings
# deploy/Caddyfile to the version in <ref> and appends every marked block back. The file is
# rewritten in place (same inode), because the Caddy container mounts that single file and
# would not see a replaced one.
#
# Usage (as root, from the checkout):
#   keep-caddy-sites.sh <ref>                  take deploy/Caddyfile from <ref>, keep the blocks
#   keep-caddy-sites.sh --restore <old-copy>   append the blocks of <old-copy> back after a reset
set -euo pipefail

CADDYFILE="deploy/Caddyfile"
BACKUP_DIR="${CADDY_BACKUP_DIR:-/var/lib/creation/caddy-backups}"

blocks() { awk '/^# >>> /{keep=1} keep{print} /^# <<< /{keep=0}' "$1"; }

# Writes <base> followed by the marked blocks of <source> into <out>.
compose() {
  local base="$1" source="$2" out="$3" kept
  kept="$(blocks "$source")"
  cat "$base" > "$out"
  if [ -n "$kept" ]; then
    printf '\n%s\n' "$kept" >> "$out"
  fi
}

caddy_container() {
  command -v docker >/dev/null 2>&1 || return 0
  docker ps --filter 'label=com.docker.compose.service=caddy' --format '{{.Names}}' 2>/dev/null | head -1
}

# Makes the running Caddy serve the file on disk. Returns non-zero when the file is invalid.
reload_caddy() {
  local ct
  ct="$(caddy_container)"
  [ -n "$ct" ] || return 0
  # A container started before the file was ever replaced by git still has the old inode
  # mounted; a restart mounts the file on disk again.
  if ! docker exec "$ct" cat /etc/caddy/Caddyfile 2>/dev/null | cmp -s - "$CADDYFILE"; then
    docker restart "$ct" >/dev/null
    sleep 2
  fi
  docker exec "$ct" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 || return 1
  docker exec "$ct" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 || return 1
}

replace_keeping_inode() {
  local new="$1" backup
  cmp -s "$new" "$CADDYFILE" && return 0
  mkdir -p "$BACKUP_DIR"
  backup="$BACKUP_DIR/Caddyfile.$(date +%Y%m%d-%H%M%S)"
  cp -p "$CADDYFILE" "$backup"
  cat "$new" > "$CADDYFILE"
  if ! reload_caddy; then
    cat "$backup" > "$CADDYFILE"
    reload_caddy || true
    echo "WARNING: the new Caddyfile did not validate, so the previous one was put back ($backup)." >&2
    return 1
  fi
}

case "${1:-}" in
  --restore)
    old="${2:?usage: keep-caddy-sites.sh --restore <old-copy>}"
    [ -f "$old" ] || exit 0
    tmp="$(mktemp)"
    trap 'rm -f "$tmp"' EXIT
    compose "$CADDYFILE" "$old" "$tmp"
    cat "$tmp" > "$CADDYFILE"
    ;;
  "" | -*)
    echo "usage: keep-caddy-sites.sh <ref> | --restore <old-copy>" >&2
    exit 2
    ;;
  *)
    ref="$1"
    base="$(mktemp)"
    new="$(mktemp)"
    trap 'rm -f "$base" "$new"' EXIT
    git show "$ref:$CADDYFILE" > "$base"
    compose "$base" "$CADDYFILE" "$new"
    if replace_keeping_inode "$new"; then
      # The index carries <ref>'s version, so a later fast-forward to <ref> leaves the file (and
      # the blocks in it) alone instead of refusing over local changes.
      git update-index --cacheinfo "100644,$(git rev-parse "$ref:$CADDYFILE"),$CADDYFILE"
      count="$(blocks "$CADDYFILE" | grep -c '^# >>> ' || true)"
      echo "== Caddyfile from $ref; sites kept from other projects: $count =="
    fi
    ;;
esac
