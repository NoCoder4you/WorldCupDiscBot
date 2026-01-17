#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/pi/WorldCupDiscBot}"
BRANCH="${BRANCH:-main}"
VENV_DIR="${VENV_DIR:-/home/pi/WorldCupDiscBot/WCenv}"
PYBIN="$VENV_DIR/bin/python"

BOT_DIR="$PROJECT_DIR/WorldCupBot"
JSON_DIR="$BOT_DIR/JSON"
BACKUPS_DIR="$BOT_DIR/BACKUPS"
CONFIG_PATH="$BOT_DIR/config.json"

echo "[updater] Project: $PROJECT_DIR"
echo "[updater] Branch:  $BRANCH"
echo "[updater] Venv:    $VENV_DIR"

if [[ ! -d "$PROJECT_DIR/.git" ]]; then
  echo "[updater] ERROR: $PROJECT_DIR is not a git repo."
  exit 1
fi

cd "$PROJECT_DIR"

echo "[updater] Fetch..."
git fetch --all --prune

echo "[updater] Preserve runtime data under $BOT_DIR"
if git ls-files --error-unmatch "$CONFIG_PATH" >/dev/null 2>&1; then
  git update-index --skip-worktree -- "$CONFIG_PATH"
fi

git ls-files -z "$JSON_DIR/" | xargs -0 -r git update-index --skip-worktree --
git ls-files -z "$BACKUPS_DIR/" | xargs -0 -r git update-index --skip-worktree --

echo "[updater] Reset to origin/$BRANCH"
git reset --hard "origin/$BRANCH"

echo "[updater] Pull..."
git pull origin "$BRANCH" --ff-only || true

if [[ ! -d "$VENV_DIR" ]]; then
  echo "[updater] Creating venv at $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

echo "[updater] Upgrade pip"
"$PYBIN" -m pip install --upgrade pip wheel setuptools

if [[ -f "$PROJECT_DIR/requirements.txt" ]]; then
  echo "[updater] Installing requirements"
  "$PYBIN" -m pip install -r "$PROJECT_DIR/requirements.txt"
fi

echo "[updater] Exec launcher.py (no git in launcher)"
exec "$PYBIN" "$PROJECT_DIR/launcher.py"
