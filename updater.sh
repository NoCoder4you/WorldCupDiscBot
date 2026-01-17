#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/NoCoder4you/WorldCupDiscBot.git"

TARGET="/home/pi/WorldCupDiscBot"
CACHE_BASE="/home/pi/.repo_cache"
CACHE="$CACHE_BASE/WorldCupDiscBot"

BOT_DIR="WorldCupBot"
JSON_DIR="$BOT_DIR/JSON/"
BACKUPS_DIR="$BOT_DIR/BACKUPS/"
CONFIG_PATH="$BOT_DIR/config.json"

VENV_DIR="$TARGET/WCenv"
PYBIN="$VENV_DIR/bin/python"
REQUIREMENTS_PATH="$TARGET/$BOT_DIR/requirements.txt"

echo "[Updater] Cache:  $CACHE"
echo "[Updater] Target: $TARGET"
echo "[Updater] Repo:   $REPO_URL"
echo "----------------------------------"

mkdir -p "$TARGET" "$CACHE_BASE"

if [[ ! -d "$CACHE/.git" ]]; then
  echo "[Updater] Creating cache..."
  rm -rf "$CACHE"
  git clone "$REPO_URL" "$CACHE"
else
  echo "[Updater] Updating cache..."
  git -C "$CACHE" fetch --all --prune
fi

# Determine default branch robustly
BRANCH="$(git -C "$CACHE" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@' || true)"
if [[ -z "${BRANCH:-}" ]]; then
  # fallback if origin/HEAD isn't set
  if git -C "$CACHE" show-ref --verify --quiet refs/remotes/origin/main; then
    BRANCH="main"
  elif git -C "$CACHE" show-ref --verify --quiet refs/remotes/origin/master; then
    BRANCH="master"
  else
    BRANCH="main"
  fi
fi

echo "[Updater] Branch: $BRANCH"

git -C "$CACHE" reset --hard "origin/$BRANCH"
git -C "$CACHE" submodule update --init --recursive

echo "----------------------------------"
echo "[Updater] Syncing files..."

rsync -a --delete \
  --exclude='.git' \
  --exclude='.repo_cache' \
  --exclude="$JSON_DIR" \
  --exclude="$BACKUPS_DIR" \
  --exclude="$CONFIG_PATH" \
  "$CACHE/" "$TARGET/"

echo "[Updater] Sync complete -> $TARGET"

echo "----------------------------------"
if [[ ! -d "$VENV_DIR" ]]; then
  echo "[Updater] Creating venv at $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

echo "[Updater] Upgrade pip"
"$PYBIN" -m pip install --upgrade pip wheel setuptools

if [[ -f "$REQUIREMENTS_PATH" ]]; then
  echo "[Updater] Installing requirements"
  "$PYBIN" -m pip install -r "$REQUIREMENTS_PATH"
fi
