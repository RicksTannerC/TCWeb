#!/usr/bin/env python
"""Back up (and verify/restore) the storefront's real data.  Standard library only.

    python deploy/backup.py                                  # back up D:\\TCData
    python deploy/backup.py --source D:\\TCData --dest E:\\TCBackups --keep 14
    python deploy/backup.py --verify                         # test-restore the newest backup
    python deploy/backup.py --verify D:\\TCData\\backups\\2026-10-10_030000
    python deploy/backup.py --restore-to C:\\Restore --from <backup folder>

What goes in a backup folder (<dest>\\<YYYY-MM-DD_HHMMSS>\\):

    db.sqlite3      copied with SQLite's ONLINE backup API, so it is consistent
                    even while the app is running and writing to it (a plain file
                    copy of a live database can be torn or miss recent writes)
    private_media\\  the private print-ready artwork originals
    media\\          the public product images (only if the folder exists)
    manifest.json   row counts, file counts/sizes and checksums, used by --verify

Never copied, on purpose: `.env` (secrets; keep it in a password manager),
`*.log`, and anything else in the source folder.  Only those three items are
ever read from the source, and the source is only ever read, never written.

A backup is built in a hidden staging folder inside --dest and renamed into
place only once the copied database passes `PRAGMA integrity_check`, so a
failed or interrupted run never leaves a half-written backup that looks real
and never deletes older good backups (retention only runs after a success).

Exit status: 0 on success / PASS, 1 on any failure / FAIL.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

DEFAULT_SOURCE = Path(r"D:\TCData")
DEFAULT_KEEP = 14

DB_NAME = "db.sqlite3"
MANIFEST_NAME = "manifest.json"
PRIVATE_MEDIA = "private_media"
MEDIA = "media"
MEDIA_FOLDERS = (PRIVATE_MEDIA, MEDIA)
LOG_NAME = "backup.log"
MANIFEST_FORMAT = 1

# Shown in the summary line so a glance tells you the important data arrived.
KEY_TABLES = ("shop_order", "shop_orderitem", "shop_listing", "shop_design")

# Backup folders are named exactly like this; retention only ever touches
# folders that match, so anything else you keep in --dest is left alone.
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}$")
TIMESTAMP_FORMAT = "%Y-%m-%d_%H%M%S"
PARTIAL_PREFIX = ".partial-"
PARTIAL_MAX_AGE_SECONDS = 24 * 60 * 60  # leftovers of a crashed run get tidied up

CHUNK = 1024 * 1024


class BackupError(Exception):
    """Anything that should fail the run with a clear message and exit 1."""


class RestoreRefused(BackupError):
    """A restore target that already exists / already holds data."""


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def _excluded(name):
    """Secrets and logs are never backed up, even if they sit inside a media folder."""
    lowered = name.lower()
    return lowered == ".env" or lowered.startswith(".env.") or lowered.endswith(".log")


def _rmtree(path):
    def on_error(func, failing_path, exc):
        # Windows refuses to delete read-only files; clear the flag and retry.
        try:
            os.chmod(failing_path, 0o700)
            func(failing_path)
        except OSError:
            pass

    shutil.rmtree(path, onexc=on_error)
    if Path(path).exists():
        raise BackupError(f"could not fully remove {path}")


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _readonly_uri(path):
    return Path(path).resolve().as_uri() + "?mode=ro"


def _quote_identifier(name):
    return '"' + name.replace('"', '""') + '"'


def _is_inside(child, parent):
    try:
        Path(child).resolve().relative_to(Path(parent).resolve())
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------
# media folders
# --------------------------------------------------------------------------

def _walk_files(root):
    """Yield (posix relative path, absolute path) for every regular file under
    root, sorted, skipping excluded names and anything that is a symlink."""
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(
            d for d in dirnames
            if not _excluded(d) and not os.path.islink(os.path.join(dirpath, d))
        )
        for filename in sorted(filenames):
            full = Path(dirpath) / filename
            if _excluded(filename) or full.is_symlink():
                continue
            yield full.relative_to(root).as_posix(), full


def _folder_size(root):
    return sum(path.stat().st_size for _rel, path in _walk_files(root))


def _copy_folder(src, dst):
    """Copy src into dst (created), returning the manifest entry for it."""
    src, dst = Path(src), Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    files = {}
    total = 0
    for rel, path in _walk_files(src):
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with open(path, "rb") as reader, open(target, "wb") as writer:
            for chunk in iter(lambda: reader.read(CHUNK), b""):
                writer.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        shutil.copystat(path, target)
        files[rel] = {"bytes": size, "sha256": digest.hexdigest()}
        total += size
    return {"present": True, "file_count": len(files), "total_bytes": total, "files": files}


def _describe_folder(root):
    """Manifest-shaped description of an existing folder, hashing what is there."""
    files = {}
    total = 0
    for rel, path in _walk_files(root):
        size = path.stat().st_size
        files[rel] = {"bytes": size, "sha256": _sha256_file(path)}
        total += size
    return {"present": True, "file_count": len(files), "total_bytes": total, "files": files}


# --------------------------------------------------------------------------
# the database
# --------------------------------------------------------------------------

def _online_copy(src_db, dst_db):
    """Copy a (possibly busy) SQLite database with the online backup API.

    The source is opened read-only, so this can never modify the live file.
    """
    try:
        src = sqlite3.connect(_readonly_uri(src_db), uri=True, timeout=30)
        try:
            dst = sqlite3.connect(str(dst_db))
            try:
                # A few hundred pages at a time, so a writer in the running
                # app is never locked out for the whole copy.
                src.backup(dst, pages=256, sleep=0.01)
                # A WAL-mode source would otherwise leave the copy in WAL mode,
                # spawning -wal/-shm side files; keep the backup one plain file.
                dst.execute("PRAGMA journal_mode=DELETE").fetchall()
            finally:
                dst.close()
        finally:
            src.close()
    except sqlite3.Error as exc:
        raise BackupError(f"could not read the source database {src_db}: {exc}") from exc


def inspect_database(path):
    """Return (integrity_check_result, {table: row count}) for a database file."""
    try:
        conn = sqlite3.connect(_readonly_uri(path), uri=True, timeout=30)
        try:
            rows = conn.execute("PRAGMA integrity_check").fetchall()
            integrity = "ok" if rows == [("ok",)] else "; ".join(str(r[0]) for r in rows[:5])
            names = [
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' "
                    "AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\' ORDER BY name"
                )
            ]
            counts = {
                name: conn.execute(f"SELECT COUNT(*) FROM {_quote_identifier(name)}").fetchone()[0]
                for name in names
            }
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise BackupError(f"{path} is not a readable database: {exc}") from exc
    return integrity, counts


# --------------------------------------------------------------------------
# making a backup
# --------------------------------------------------------------------------

def list_backups(dest):
    """Timestamped backup folders in dest, oldest first."""
    dest = Path(dest)
    if not dest.is_dir():
        return []
    return sorted(
        entry for entry in dest.iterdir()
        if TIMESTAMP_RE.match(entry.name) and entry.is_dir() and not entry.is_symlink()
    )


def apply_retention(dest, keep, protect=None):
    """Delete all but the newest `keep` timestamped folders in dest.

    Only folders whose names match the timestamp pattern are ever touched.
    Returns the names that were removed.
    """
    backups = list_backups(dest)
    doomed = backups[:-keep] if keep > 0 else []
    removed = []
    for entry in doomed:
        if protect is not None and entry.name == protect:
            continue
        _rmtree(entry)
        removed.append(entry.name)
    return removed


def _tidy_partials(dest):
    cutoff = time.time() - PARTIAL_MAX_AGE_SECONDS
    for entry in Path(dest).iterdir():
        if entry.name.startswith(PARTIAL_PREFIX) and entry.is_dir() and not entry.is_symlink():
            try:
                if entry.stat().st_mtime < cutoff:
                    _rmtree(entry)
            except (OSError, BackupError):
                pass


def make_backup(source, dest, keep=DEFAULT_KEEP, now=None, log=print):
    """Create one backup of `source` inside `dest`; return its folder.

    Raises BackupError on any failure, leaving existing backups untouched.
    """
    source, dest = Path(source), Path(dest)
    if keep < 1:
        raise BackupError("--keep must be at least 1")
    if not source.is_dir():
        raise BackupError(f"source folder not found: {source}")
    src_db = source / DB_NAME
    if not src_db.is_file():
        raise BackupError(f"no database at {src_db}")
    for folder in MEDIA_FOLDERS:
        if _is_inside(dest, source / folder):
            raise BackupError(
                f"--dest {dest} is inside {source / folder}; "
                "choose a folder outside the media folders"
            )

    dest.mkdir(parents=True, exist_ok=True)

    # Refuse early rather than fill the disk half way through.
    needed = src_db.stat().st_size
    for folder in MEDIA_FOLDERS:
        if (source / folder).is_dir():
            needed += _folder_size(source / folder)
    free = shutil.disk_usage(dest).free
    if free < needed * 1.1 + 10 * 1024 * 1024:
        raise BackupError(
            f"not enough free space in {dest}: need about {needed // (1024 * 1024)} MB, "
            f"{free // (1024 * 1024)} MB free"
        )

    _tidy_partials(dest)
    staging = dest / f"{PARTIAL_PREFIX}{os.getpid()}-{time.time_ns()}"
    staging.mkdir()
    try:
        log(f"Copying database from {src_db} (online backup)")
        staged_db = staging / DB_NAME
        _online_copy(src_db, staged_db)

        integrity, tables = inspect_database(staged_db)
        if integrity != "ok":
            raise BackupError(f"integrity_check failed on the copied database: {integrity}")
        if not tables:
            raise BackupError(
                f"the database at {src_db} has no tables; refusing to back up an empty database"
            )
        log(f"Database copied; integrity_check ok; {len(tables)} tables")

        folders = {}
        for folder in MEDIA_FOLDERS:
            src_folder = source / folder
            if src_folder.is_dir():
                log(f"Copying {folder}\\")
                folders[folder] = _copy_folder(src_folder, staging / folder)
            elif folder == PRIVATE_MEDIA:
                # Always present in a backup, even if empty/missing at the source.
                (staging / folder).mkdir()
                folders[folder] = {"present": False, "file_count": 0, "total_bytes": 0, "files": {}}
            else:
                folders[folder] = {"present": False, "file_count": 0, "total_bytes": 0, "files": {}}

        # Hash last, after every read of the database copy is finished.
        manifest = {
            "format": MANIFEST_FORMAT,
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "source": str(source),
            "sqlite_version": sqlite3.sqlite_version,
            "database": {
                "file": DB_NAME,
                "bytes": staged_db.stat().st_size,
                "sha256": _sha256_file(staged_db),
                "integrity_check": integrity,
                "tables": tables,
            },
            "folders": folders,
        }
        (staging / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )

        final = _place(staging, dest, now)
    except BaseException:
        if staging.exists():
            _rmtree(staging)
        raise

    removed = apply_retention(dest, keep, protect=final.name)
    if removed:
        log(f"Retention (keep {keep}): removed {len(removed)} old backup(s): {', '.join(removed)}")
    log(f"Backup complete: {final}")
    return final


def _place(staging, dest, now=None):
    """Rename the finished staging folder to a free timestamped name.

    Two runs in the same second never collide: the later one takes the next
    free second instead of overwriting or failing.
    """
    stamp = now or datetime.datetime.now()
    while True:
        target = dest / stamp.strftime(TIMESTAMP_FORMAT)
        if not target.exists():
            try:
                os.rename(staging, target)
                return target
            except OSError:
                if not target.exists():
                    raise
        stamp += datetime.timedelta(seconds=1)


# --------------------------------------------------------------------------
# restoring and verifying
# --------------------------------------------------------------------------

def _load_manifest(backup_dir):
    path = Path(backup_dir) / MANIFEST_NAME
    if not path.is_file():
        raise BackupError(f"{backup_dir} has no {MANIFEST_NAME}; it is not a complete backup")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["database"]["tables"]
        manifest["database"]["sha256"]
        manifest["folders"]
    except (ValueError, KeyError, TypeError) as exc:
        raise BackupError(f"{path} is unreadable or incomplete: {exc}") from exc
    return manifest


def restore_backup(backup_dir, target_dir):
    """Copy a backup into a NEW (or empty) folder.

    Refuses to write onto anything that already exists with content, and in
    particular onto an existing database: restoring over live data must be a
    deliberate, manual act (stop the app, move the old files aside first).
    """
    backup_dir, target = Path(backup_dir), Path(target_dir)
    if not (backup_dir / DB_NAME).is_file():
        raise BackupError(f"{backup_dir} contains no {DB_NAME}")
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise RestoreRefused(f"refusing to restore onto {target}: it exists and is not a folder")
    if (target / DB_NAME).exists():
        raise RestoreRefused(f"refusing to overwrite the existing database {target / DB_NAME}")
    if target.is_dir() and any(target.iterdir()):
        raise RestoreRefused(f"refusing to restore into {target}: it already contains files")
    if _is_inside(target, backup_dir):
        raise RestoreRefused("the restore target must not be inside the backup folder")

    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_dir / DB_NAME, target / DB_NAME)
    for folder in MEDIA_FOLDERS:
        if (backup_dir / folder).is_dir():
            _copy_folder(backup_dir / folder, target / folder)
    return target


def _compare_folder(name, expected, root):
    problems = []
    folder = Path(root) / name
    if not expected.get("present", False) and name != PRIVATE_MEDIA:
        if folder.exists():
            problems.append(f"{name}\\ exists but the manifest says it was not backed up")
        return problems
    if not folder.is_dir():
        return [f"{name}\\ is missing"]
    actual = _describe_folder(folder)
    expected_files = expected.get("files", {})
    if actual["file_count"] != expected["file_count"]:
        problems.append(
            f"{name}\\: {actual['file_count']} files, manifest says {expected['file_count']}"
        )
    if actual["total_bytes"] != expected["total_bytes"]:
        problems.append(
            f"{name}\\: {actual['total_bytes']} bytes, manifest says {expected['total_bytes']}"
        )
    for rel in sorted(set(expected_files) - set(actual["files"])):
        problems.append(f"{name}\\{rel} is missing")
    for rel in sorted(set(actual["files"]) - set(expected_files)):
        problems.append(f"{name}\\{rel} is not in the manifest")
    for rel in sorted(set(expected_files) & set(actual["files"])):
        if actual["files"][rel] != expected_files[rel]:
            problems.append(f"{name}\\{rel} does not match its recorded size/checksum")
    return problems


def verify_backup(backup_dir, log=print):
    """Test-restore one backup into a temporary folder and compare it with its
    manifest.  Returns a list of problems; an empty list means PASS.

    Nothing is ever written outside the temporary folder, which is removed.
    """
    backup_dir = Path(backup_dir)
    if not backup_dir.is_dir():
        return [f"backup folder not found: {backup_dir}"]
    try:
        manifest = _load_manifest(backup_dir)
    except BackupError as exc:
        return [str(exc)]

    problems = []
    allowed = {DB_NAME, MANIFEST_NAME, *MEDIA_FOLDERS}
    for entry in sorted(backup_dir.iterdir()):
        if entry.name not in allowed:
            problems.append(f"unexpected item in the backup: {entry.name}")
    if problems:
        return problems

    for folder in MEDIA_FOLDERS:
        if (backup_dir / folder).is_dir():
            for dirpath, dirnames, filenames in os.walk(backup_dir / folder, followlinks=False):
                for name in dirnames + filenames:
                    full = Path(dirpath) / name
                    if _excluded(name) or full.is_symlink():
                        problems.append(
                            f"forbidden item in the backup: {full.relative_to(backup_dir).as_posix()}"
                        )
    if problems:
        return problems

    db_entry = manifest["database"]
    if (backup_dir / DB_NAME).is_file() and _sha256_file(backup_dir / DB_NAME) != db_entry["sha256"]:
        problems.append(f"{DB_NAME} does not match the checksum in the manifest")

    scratch = Path(tempfile.mkdtemp(prefix="tcweb-restore-check-"))
    try:
        try:
            restored = restore_backup(backup_dir, scratch / "restored")
        except BackupError as exc:
            return problems + [str(exc)]
        log(f"Restored into temporary folder {restored}")

        try:
            integrity, tables = inspect_database(restored / DB_NAME)
        except BackupError as exc:
            return problems + [str(exc)]
        if integrity != "ok":
            problems.append(f"integrity_check failed on the restored database: {integrity}")
        expected_tables = db_entry["tables"]
        for name in sorted(set(expected_tables) - set(tables)):
            problems.append(f"table {name} is missing from the restored database")
        for name in sorted(set(tables) - set(expected_tables)):
            problems.append(f"table {name} is not in the manifest")
        for name in sorted(set(tables) & set(expected_tables)):
            if tables[name] != expected_tables[name]:
                problems.append(
                    f"table {name}: {tables[name]} rows, manifest says {expected_tables[name]}"
                )
        for folder in MEDIA_FOLDERS:
            if folder in manifest["folders"]:
                problems.extend(_compare_folder(folder, manifest["folders"][folder], restored))
        extra = {p.name for p in restored.iterdir()} - allowed
        for name in sorted(extra - {MANIFEST_NAME}):
            problems.append(f"unexpected item after restore: {name}")
    finally:
        _rmtree(scratch)

    if not problems:
        folders = manifest["folders"]
        log(
            f"Restored database: integrity ok, {len(db_entry['tables'])} tables, "
            f"{sum(db_entry['tables'].values())} rows in total"
        )
        for folder in MEDIA_FOLDERS:
            info = folders.get(folder, {})
            log(f"Restored {folder}\\: {info.get('file_count', 0)} files, "
                f"{info.get('total_bytes', 0)} bytes, all checksums match")
    return problems


# --------------------------------------------------------------------------
# command line
# --------------------------------------------------------------------------

def _summary_lines(backup_dir):
    manifest = _load_manifest(backup_dir)
    tables = manifest["database"]["tables"]
    size = sum(f.stat().st_size for f in Path(backup_dir).rglob("*") if f.is_file())
    lines = [f"Backup folder: {backup_dir}", f"Total size: {size} bytes"]
    lines.append(f"Database: {manifest['database']['bytes']} bytes, {len(tables)} tables")
    for name in KEY_TABLES:
        if name in tables:
            lines.append(f"  {name}: {tables[name]} rows")
    for folder in MEDIA_FOLDERS:
        info = manifest["folders"].get(folder, {})
        state = "" if info.get("present") else " (not present at the source)"
        lines.append(
            f"{folder}: {info.get('file_count', 0)} files, {info.get('total_bytes', 0)} bytes{state}"
        )
    return lines


def _make_logger(dest):
    """Print to the console and, best effort, append to <dest>\\backup.log so a
    run by Task Scheduler (no console) still leaves a trail."""
    log_path = Path(dest) / LOG_NAME

    def log(message):
        print(message, flush=True)
        try:
            with open(log_path, "a", encoding="utf-8") as handle:
                stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                handle.write(f"{stamp}  {message}\n")
        except OSError:
            pass

    return log


def _pick_backup(explicit, dest):
    if explicit:
        return Path(explicit)
    backups = list_backups(dest)
    if not backups:
        raise BackupError(f"no backups found in {dest}")
    return backups[-1]


def build_parser():
    parser = argparse.ArgumentParser(
        description="Back up, verify and restore the storefront's data (see the README, Backups).",
    )
    parser.add_argument("--source", default=str(DEFAULT_SOURCE),
                        help=r"data folder holding db.sqlite3, private_media\ and media\ "
                             r"(default: D:\TCData)")
    parser.add_argument("--dest", default=None,
                        help=r"folder that receives the timestamped backups "
                             r"(default: <source>\backups)")
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP,
                        help=f"newest backups to keep (default: {DEFAULT_KEEP})")
    parser.add_argument("--verify", nargs="?", const="", default=None, metavar="BACKUP",
                        help="test-restore BACKUP (default: the newest in --dest) into a "
                             "temporary folder and compare it with its manifest")
    parser.add_argument("--restore-to", default=None, metavar="DIR",
                        help="restore a backup (--from, default newest) into DIR, which must "
                             "not already contain data")
    parser.add_argument("--from", dest="from_backup", default=None, metavar="BACKUP",
                        help="backup folder to use with --restore-to")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    source = Path(args.source)
    dest = Path(args.dest) if args.dest else source / "backups"
    log = _make_logger(dest)

    try:
        if args.verify is not None:
            backup = _pick_backup(args.verify, dest)
            log(f"Verifying {backup}")
            problems = verify_backup(backup, log=log)
            if problems:
                log(f"FAIL: {backup}")
                for problem in problems:
                    log(f"  - {problem}")
                return 1
            log(f"PASS: {backup}")
            return 0

        if args.restore_to is not None:
            backup = _pick_backup(args.from_backup, dest)
            target = restore_backup(backup, args.restore_to)
            print(f"Restored {backup} into {target}")
            print("Run `python deploy/backup.py --verify` on the backup first if unsure.")
            return 0

        started = time.time()
        final = make_backup(source, dest, keep=args.keep, log=log)
        for line in _summary_lines(final):
            log(line)
        log(f"Done in {time.time() - started:.1f}s")
        return 0
    except BackupError as exc:
        log(f"ERROR: {exc}")
        return 1
    except Exception as exc:  # a scheduled run must fail loudly, never silently
        log(f"ERROR: unexpected failure: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
