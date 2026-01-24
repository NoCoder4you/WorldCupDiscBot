import datetime
import logging
import os
import zipfile

MAX_BACKUPS = 25
log = logging.getLogger("launcher")


def _backup_dir(base_dir: str) -> str:
    path = os.path.join(base_dir, "BACKUPS")
    os.makedirs(path, exist_ok=True)
    return path


def _json_dir(base_dir: str) -> str:
    path = os.path.join(base_dir, "JSON")
    os.makedirs(path, exist_ok=True)
    return path


def _unique_backup_path(bdir: str, timestamp: str) -> tuple[str, str]:
    base_name = f"{timestamp}.zip"
    base_path = os.path.join(bdir, base_name)
    if not os.path.exists(base_path):
        return base_name, base_path
    suffix = 1
    while True:
        candidate_name = f"{timestamp}_{suffix:02d}.zip"
        candidate_path = os.path.join(bdir, candidate_name)
        if not os.path.exists(candidate_path):
            return candidate_name, candidate_path
        suffix += 1


def _cleanup_old_backups(bdir: str):
    backups = sorted(
        [
            os.path.join(bdir, name)
            for name in os.listdir(bdir)
            if name.endswith(".zip") and os.path.isfile(os.path.join(bdir, name))
        ],
        key=os.path.getmtime,
    )
    if len(backups) <= MAX_BACKUPS:
        return
    for path in backups[:-MAX_BACKUPS]:
        try:
            os.remove(path)
        except OSError:
            log.warning("Failed to remove old backup: %s", path)


def create_backup(base_dir: str) -> str:
    bdir = _backup_dir(base_dir)
    jdir = _json_dir(base_dir)
    ts = datetime.datetime.now().strftime("%d-%m_%H-%M-%S")
    outname, outpath = _unique_backup_path(bdir, ts)
    with zipfile.ZipFile(outpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
        if os.path.isdir(jdir):
            for root, _, files in os.walk(jdir):
                for fn in files:
                    fp = os.path.join(root, fn)
                    arc = os.path.relpath(fp, jdir)
                    z.write(fp, arcname=arc)
    _cleanup_old_backups(bdir)
    return outname

