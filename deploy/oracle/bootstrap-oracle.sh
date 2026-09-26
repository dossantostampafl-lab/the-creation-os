#!/usr/bin/env bash
# One-command bootstrap for THE CREATION OS on an Ubuntu Oracle Cloud VM.
# Downloads/updates the official repository and delegates to the hardened Oracle installer.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then
    exec sudo -E bash "$0" "$@"
  fi
  echo "ERROR: run this bootstrap as root or install sudo." >&2
  exit 1
fi

REPO_URL="${CREATION_REPO_URL:-https://github.com/dossantostampafl-lab/the-creation-os.git}"
REPO_DIR="${CREATION_INSTALL_DIR:-/opt/the-creation-os}"
BRANCH="${CREATION_BRANCH:-main}"

log() { printf '\n==> %s\n' "$*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

if [ ! -r /etc/os-release ]; then
  die "cannot identify the operating system; Ubuntu 22.04 or 24.04 is required"
fi
# shellcheck disable=SC1091
. /etc/os-release
if [ "${ID:-}" != "ubuntu" ]; then
  die "unsupported operating system '${ID:-unknown}'; use Ubuntu 22.04 or 24.04"
fi

log "Bootstrap prerequisites"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl git

log "THE CREATION OS repository"
if [ -d "$REPO_DIR/.git" ]; then
  origin_url="$(git -C "$REPO_DIR" remote get-url origin 2>/dev/null || true)"
  if [ "$origin_url" != "$REPO_URL" ]; then
    die "$REPO_DIR already contains a different Git repository ($origin_url)"
  fi

  # The Oracle installation directory is deployment-owned. Runtime secrets live in the
  # untracked .env and application data lives in Docker volumes, so updating tracked files
  # to the audited main branch does not erase either one.
  git -C "$REPO_DIR" fetch --prune origin main
  git -C "$REPO_DIR" checkout -q main
  git -C "$REPO_DIR" reset --hard origin/main
else
  if [ -e "$REPO_DIR" ] && [ -n "$(ls -A "$REPO_DIR" 2>/dev/null || true)" ]; then
    die "$REPO_DIR exists and is not an empty THE CREATION OS installation directory"
  fi
  mkdir -p "$(dirname "$REPO_DIR")"
  git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$REPO_DIR"
fi

cd "$REPO_DIR"
chmod +x deploy/oracle/install.sh

log "Oracle production installation"
exec bash deploy/oracle/install.sh
