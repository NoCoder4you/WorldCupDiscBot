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
    return datetime.now().strftime("%d-%m_%H-%M")

def backup_all_json():
    ensure_backup_dir()
    json_files = [f for f in os.listdir(JSON_DIR) if f.endswith(".json")]
    timestamp = get_timestamp()
    backup_paths = []
    for file in json_files:
        src = os.path.join(JSON_DIR, file)
        dst = os.path.join(BACKUP_DIR, f"{file.rsplit('.', 1)[0]}_{timestamp}.zip")
        with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(src, arcname=file)
        backup_paths.append(dst)
    cleanup_old_backups()
    log.info("Backup created (count=%s timestamp=%s)", len(backup_paths), timestamp)
    return backup_paths

def cleanup_old_backups():
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
    base = filename.rsplit('.', 1)[0]
    backups = [
        f for f in os.listdir(BACKUP_DIR)
        if f.startswith(base) and f.endswith(".zip")
    ]
    if not backups:
        return None
    latest_backup = sorted(backups, reverse=True)[0]
    src = os.path.join(BACKUP_DIR, latest_backup)
    dst = os.path.join(JSON_DIR, filename)
    with zipfile.ZipFile(src, "r") as zf:
        with zf.open(filename) as zipped_file, open(dst, "wb") as out:
            shutil.copyfileobj(zipped_file, out)
    return src

class BackupRestore(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auto_backup.start()

    @tasks.loop(hours=6)
    async def auto_backup(self):
        backup_all_json()
        log.info("Auto backup completed")

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
