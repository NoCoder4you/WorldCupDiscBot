import discord
from discord.ext import commands, tasks
import os
import shutil
import logging
import zipfile
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
JSON_DIR = BASE_DIR / "JSON"
BACKUP_DIR = BASE_DIR / "BACKUPS"
MAX_BACKUPS = 25

log = logging.getLogger(__name__)

def ensure_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)

def get_timestamp():
    return datetime.now().strftime("%d-%m_%H-%M-%S")

def unique_backup_path(timestamp: str) -> str:
    """Return a non-colliding backup path for the given timestamp."""
    ensure_backup_dir()
    base = BACKUP_DIR / f"{timestamp}.zip"
    if not base.exists():
        return str(base)
    suffix = 1
    while True:
        candidate = BACKUP_DIR / f"{timestamp}_{suffix:02d}.zip"
        if not candidate.exists():
            return str(candidate)
        suffix += 1

def backup_all_json():
    ensure_backup_dir()
    json_files = [f for f in os.listdir(JSON_DIR) if f.endswith(".json")]
    timestamp = get_timestamp()
    dst = unique_backup_path(timestamp)
    with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in json_files:
            src = os.path.join(JSON_DIR, file)
            zf.write(src, arcname=file)
    cleanup_old_backups()
    log.info("Backup created (count=%s timestamp=%s)", len(json_files), timestamp)
    return [dst]

def cleanup_old_backups():
    if not BACKUP_DIR.exists():
        return
    all_backups = sorted([
        os.path.join(BACKUP_DIR, f)
        for f in os.listdir(BACKUP_DIR) if f.endswith(".zip")
    ], key=os.path.getmtime)
    if len(all_backups) > MAX_BACKUPS:
        for file in all_backups[:-MAX_BACKUPS]:
            try:
                os.remove(file)
            except Exception:
                pass

def restore_json(filename: str):
    """Restore a specific file from the most recent backup."""
    backups = [
        os.path.join(BACKUP_DIR, f)
        for f in os.listdir(BACKUP_DIR)
        if f.endswith(".zip")
    ]
    if not backups:
        return None
    src = max(backups, key=os.path.getmtime)
    dst = os.path.join(JSON_DIR, filename)
    with zipfile.ZipFile(src, "r") as zf:
        try:
            with zf.open(filename) as zipped_file, open(dst, "wb") as out:
                shutil.copyfileobj(zipped_file, out)
        except KeyError:
            return None
    return src

class BackupRestore(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auto_backup.start()

    @tasks.loop(hours=6)
    async def auto_backup(self):
        backup_all_json()
        log.info("Auto backup completed")

    @auto_backup.before_loop
    async def before_auto_backup(self):
        await self.bot.wait_until_ready()

    @commands.command(name="backup", help="Manually backup all JSON files to the BACKUPS folder.")
    @commands.is_owner()
    async def manual_backup(self, ctx):
        files = backup_all_json()
        log.info("Manual backup requested by %s (count=%s)", ctx.author, len(files))
        await ctx.send(f"Backed up {len(files)} JSON files to BACKUPS folder.", delete_after=10)

    @commands.command(name="restore", help="Restore a JSON file from latest backup. Usage: wc restore players.json")
    @commands.is_owner()
    async def manual_restore(self, ctx, filename: str):
        if not filename.endswith(".json"):
            await ctx.send("Please specify a valid JSON file name.", delete_after=7)
            return
        result = restore_json(filename)
        if result:
            log.info("Manual restore requested by %s (file=%s)", ctx.author, filename)
            await ctx.send(f"Restored `{filename}` from backup.", delete_after=10)
        else:
            await ctx.send(f"No backups found for `{filename}`.", delete_after=10)

async def setup(bot):
    await bot.add_cog(BackupRestore(bot))
