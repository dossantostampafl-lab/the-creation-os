#!/usr/bin/env bash
# Reports every checkout of this project on the server, and parks the ones that are not the
# one serving. It deletes nothing: a checkout is moved aside, never removed, so an unwanted
# move is one mv away from undone and no data can be lost to a mistake here.
#
#   sudo ./deploy/oracle/tidy-server.sh            # report only
#   sudo ./deploy/oracle/tidy-server.sh --park     # report, then park the dormant ones
#
# Why parking is worth doing. Compose takes its project name from the directory's name, and
# every checkout here is named the-creation-os -- so a command run in the dormant copy acts on
# the live project: the same containers, the same volumes. `docker compose down -v` typed in
# the wrong window would take the database with it. Renaming the directory gives that copy a
# project name of its own, which is what makes the mistake harmless.
set -uo pipefail

if [ "$(id -u)" -ne 0 ]; then
  exec sudo -E bash "$0" "$@"
fi

park=false
[ "${1:-}" = "--park" ] && park=true

# Where something that starts a checkout on its own would be configured. Overridable so the
# tests can exercise the refusal against directories they control, rather than the real ones.
read -r -a REFERENCE_PATHS <<< "${TIDY_REFERENCE_PATHS:-/etc/systemd/system /etc/cron.d /var/spool/cron}"

# A directory that something else starts must not move under it.
references_to() {
  grep -rl -F "$1" "${REFERENCE_PATHS[@]}" 2>/dev/null | tr '\n' ' ' | sed 's/ $//' || true
}

echo "== The installation that is serving =="
api_container="$(docker ps --filter 'label=com.docker.compose.service=api' --format '{{.ID}}' | head -1)"
if [ -z "$api_container" ]; then
  echo "   No api container is running. Nothing will be parked: without knowing which"
  echo "   installation is live, every one of them has to be left alone."
  exit 0
fi
live_dir="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$api_container" 2>/dev/null)"
live_project="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$api_container" 2>/dev/null)"
echo "   directory: ${live_dir:-<unknown>}"
echo "   project:   ${live_project:-<unknown>}"
if [ -z "$live_dir" ]; then
  echo "   That container does not record a directory, so nothing can be told apart. Stopping."
  exit 0
fi

echo
echo "== Volumes, and which project owns them =="
docker volume ls --format '{{.Name}}' | grep -E "^${live_project}_" | while read -r volume; do
  printf '   %s\n' "$volume"
done

echo
echo "== Other checkouts on this machine =="
mapfile -t others < <(
  find / -maxdepth 4 -name docker-compose.cloud.yml -not -path '*/.git/*' 2>/dev/null \
    | xargs -r -n1 dirname \
    | grep -Fxv "$live_dir" \
    | sort -u
)
if [ "${#others[@]}" -eq 0 ]; then
  echo "   None. The server holds one installation, which is the tidy state."
  exit 0
fi

for dir in "${others[@]}"; do
  echo
  echo "   $dir"
  printf '      same Compose project name as the live one? %s\n' \
    "$([ "$(basename "$dir")" = "$(basename "$live_dir")" ] && echo "YES -- commands there act on the live stack" || echo "no")"
  printf '      .env: %s\n' "$([ -f "$dir/.env" ] && echo "present" || echo "absent")"
  if [ -f "$dir/.env" ]; then
    printf '      .env LLM_PROVIDER=%s, ANTHROPIC_API_KEY %s\n' \
      "$(grep -E '^LLM_PROVIDER=' "$dir/.env" | tail -1 | cut -d= -f2-)" \
      "$(grep -qE '^ANTHROPIC_API_KEY=.+' "$dir/.env" && echo "set" || echo "empty")"
  fi
  # Anything that starts this copy on its own would break if it moved, so it is reported first.
  printf '      started by something else? %s\n' "$(references_to "$dir" || echo "nothing found")"
done

if [ "$park" != true ]; then
  echo
  echo "Report only. Run with --park to move these aside."
  exit 0
fi

echo
echo "== Parking =="
for dir in "${others[@]}"; do
  referenced="$(references_to "$dir")"
  if [ -n "$referenced" ]; then
    echo "   $dir stays: it is referenced by $referenced. Deal with that first."
    continue
  fi
  destination="$dir.parked-$(date +%Y%m%d)"
  if [ -e "$destination" ]; then
    echo "   $destination already exists; leaving $dir alone."
    continue
  fi
  mv "$dir" "$destination"
  cat > "$destination/PARKED.md" <<PARKED
This checkout is not the one serving. It was moved aside on $(date -u +%Y-%m-%d) by
deploy/oracle/tidy-server.sh, because it shared a Compose project name with the live
installation at $live_dir -- so a command run here acted on the live stack's containers
and volumes.

Nothing was deleted. To undo:

    sudo mv "$destination" "$dir"
PARKED
  echo "   $dir -> $destination  (nothing deleted; PARKED.md explains how to undo)"
done

echo
echo "Done. The live installation at $live_dir was not touched."
