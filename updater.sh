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

backup_dir() {
  local source_dir="$1"
  local exclude_pattern="$2"
  local backup_dir

  if [[ ! -d "$source_dir" ]]; then
    echo ""
    return 0
  fi

  backup_dir="$(mktemp -d)"
  echo "[updater] Backup $source_dir -> $backup_dir"
  if [[ -n "$exclude_pattern" ]]; then
    rsync -a --exclude "$exclude_pattern" "$source_dir/" "$backup_dir/"
  else
    rsync -a "$source_dir/" "$backup_dir/"
  fi
  echo "$backup_dir"
}

restore_dir() {
  local backup_dir="$1"
  local target_dir="$2"
  local exclude_pattern="$3"

  if [[ -z "$backup_dir" ]]; then
    return 0
  fi

  echo "[updater] Restore $target_dir from backup"
  rm -rf "$target_dir"
  mkdir -p "$target_dir"
  if [[ -n "$exclude_pattern" ]]; then
    rsync -a --exclude "$exclude_pattern" "$backup_dir/" "$target_dir/"
  else
    rsync -a "$backup_dir/" "$target_dir/"
  fi
  rm -rf "$backup_dir"
}

backup_file() {
  local source_file="$1"
  local backup_file

  if [[ ! -f "$source_file" ]]; then
    echo ""
    return 0
  fi

  backup_file="$(mktemp)"
  echo "[updater] Backup $source_file -> $backup_file"
  cp -a "$source_file" "$backup_file"
  echo "$backup_file"
}

restore_file() {
  local backup_file="$1"
  local target_file="$2"

  if [[ -z "$backup_file" ]]; then
    return 0
  fi

  echo "[updater] Restore $target_file from backup"
  mkdir -p "$(dirname "$target_file")"
  cp -a "$backup_file" "$target_file"
  rm -f "$backup_file"
}

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

JSON_BACKUP_DIR="$(backup_dir "$JSON_DIR" "backup/")"
BACKUPS_BACKUP_DIR="$(backup_dir "$BACKUPS_DIR" "")"
CONFIG_BACKUP_PATH="$(backup_file "$CONFIG_PATH")"

echo "[updater] Reset to origin/$BRANCH"
git reset --hard "origin/$BRANCH"

echo "[updater] Pull..."
git pull origin "$BRANCH" --ff-only || true

restore_dir "$JSON_BACKUP_DIR" "$JSON_DIR" "backup/"
restore_dir "$BACKUPS_BACKUP_DIR" "$BACKUPS_DIR" ""
restore_file "$CONFIG_BACKUP_PATH" "$CONFIG_PATH"

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
