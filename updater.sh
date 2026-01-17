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
VENV_REL="WCenv/"

LAST_SYNC_FILE="$TARGET/.last_update_commit"

EXCLUDE_PATHS=(
  ".git"
  ".repo_cache"
  "$JSON_DIR"
  "$BACKUPS_DIR"
  "$CONFIG_PATH"
  "$VENV_REL"
  "updater.sh"
)

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

NEW_COMMIT="$(git -C "$CACHE" rev-parse "origin/$BRANCH")"
LAST_COMMIT=""
if [[ -f "$LAST_SYNC_FILE" ]]; then
  LAST_COMMIT="$(<"$LAST_SYNC_FILE")"
fi

echo "----------------------------------"
if [[ -n "$LAST_COMMIT" ]] && git -C "$CACHE" cat-file -e "$LAST_COMMIT^{commit}" 2>/dev/null; then
  echo "[Updater] Syncing changed files since $LAST_COMMIT..."
  TMP_LIST="$(mktemp)"
  git -C "$CACHE" diff --name-only -z "$LAST_COMMIT" "$NEW_COMMIT" \
    | while IFS= read -r -d '' path; do
        case "$path" in
          "$JSON_DIR"*|"$BACKUPS_DIR"*|"$CONFIG_PATH"|"$VENV_REL"*|"updater.sh")
            continue
            ;;
        esac
        printf '%s\0' "$path" >> "$TMP_LIST"
      done

  if [[ -s "$TMP_LIST" ]]; then
    rsync -a --from0 --files-from="$TMP_LIST" "$CACHE/" "$TARGET/"
  else
    echo "[Updater] No tracked changes to sync."
  fi

  while IFS= read -r -d '' status; do
    case "$status" in
      D*)
        IFS= read -r -d '' path
        case "$path" in
          "$JSON_DIR"*|"$BACKUPS_DIR"*|"$CONFIG_PATH"|"$VENV_REL"*|"updater.sh")
            continue
            ;;
        esac
        rm -f "$TARGET/$path"
        ;;
      R*|C*)
        IFS= read -r -d '' old_path
        IFS= read -r -d '' new_path
        case "$old_path" in
          "$JSON_DIR"*|"$BACKUPS_DIR"*|"$CONFIG_PATH"|"$VENV_REL"*|"updater.sh")
            continue
            ;;
        esac
        rm -f "$TARGET/$old_path"
        ;;
      *)
        IFS= read -r -d '' _path
        ;;
    esac
  done < <(git -C "$CACHE" diff --name-status -z "$LAST_COMMIT" "$NEW_COMMIT")

  rm -f "$TMP_LIST"
else
  echo "[Updater] Syncing all files..."
  rsync -a --delete \
    --exclude='.git' \
    --exclude='.repo_cache' \
    --exclude="$JSON_DIR" \
    --exclude="$BACKUPS_DIR" \
    --exclude="$CONFIG_PATH" \
    --exclude="$VENV_REL" \
    --exclude='updater.sh' \
    "$CACHE/" "$TARGET/"
fi

echo "$NEW_COMMIT" > "$LAST_SYNC_FILE"

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
