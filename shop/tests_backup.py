"""deploy/backup.py: the real, tested backup + restore check.

Everything here runs in temporary directories against a small fabricated
SQLite database; nothing touches the real data folder or the network.  The
script is loaded as a module (it has no dependencies) and, for the exit-status
checks, also run as a real subprocess exactly as Task Scheduler would.
"""

import datetime
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "backup.py"

_spec = importlib.util.spec_from_file_location("tcweb_backup_script", SCRIPT)
backup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backup)

SECRET = "STRIPE_SECRET_KEY=sk_live_not_a_real_key"


def quiet(_message):
    pass


def make_database(path, orders=3, listings=2, designs=4, wal=False):
    conn = sqlite3.connect(str(path))
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        """
        CREATE TABLE shop_order (id INTEGER PRIMARY KEY, email TEXT, total INTEGER);
        CREATE TABLE shop_listing (id INTEGER PRIMARY KEY, title TEXT);
        CREATE TABLE shop_design (id INTEGER PRIMARY KEY, name TEXT);
        CREATE INDEX shop_order_email ON shop_order (email);
        """
    )
    conn.executemany(
        "INSERT INTO shop_order (email, total) VALUES (?, ?)",
        [(f"buyer{i}@example.com", 2500 + i) for i in range(orders)],
    )
    conn.executemany("INSERT INTO shop_listing (title) VALUES (?)",
                     [(f"Tee {i}",) for i in range(listings)])
    conn.executemany("INSERT INTO shop_design (name) VALUES (?)",
                     [(f"Design {i}",) for i in range(designs)])
    conn.commit()
    conn.close()


class BackupTestCase(SimpleTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="tcweb-backup-test-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.source = self.tmp / "TCData"
        self.dest = self.tmp / "backups"
        self.source.mkdir()
        make_database(self.source / "db.sqlite3")
        (self.source / "private_media").mkdir()
        (self.source / "private_media" / "front.png").write_bytes(b"\x89PNG" + b"A" * 5000)
        (self.source / "private_media" / "sub").mkdir()
        (self.source / "private_media" / "sub" / "back.png").write_bytes(b"\x89PNG" + b"B" * 300)
        (self.source / "media").mkdir()
        (self.source / "media" / "mockup.jpg").write_bytes(b"JPG" * 100)
        # Things that live next to the data but must never be backed up.
        (self.source / ".env").write_text(SECRET, encoding="utf-8")
        (self.source / "waitress.log").write_text("log line", encoding="utf-8")
        (self.source / "db-before-0009.sqlite3").write_bytes(b"old hand-made copy")
        (self.source / "notes.txt").write_text("unrelated", encoding="utf-8")

    def run_backup(self, **kwargs):
        kwargs.setdefault("log", quiet)
        return backup.make_backup(self.source, self.dest, **kwargs)

    def manifest_of(self, folder):
        return json.loads((Path(folder) / "manifest.json").read_text(encoding="utf-8"))

    def snapshot(self, root):
        out = {}
        for path in sorted(Path(root).rglob("*")):
            if path.is_file():
                out[path.relative_to(root).as_posix()] = (
                    path.stat().st_size, path.stat().st_mtime_ns, backup._sha256_file(path)
                )
        return out

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            capture_output=True, text=True, timeout=120,
        )


class LayoutAndContentsTests(BackupTestCase):
    def test_backup_creates_the_expected_layout(self):
        final = self.run_backup()
        self.assertTrue(backup.TIMESTAMP_RE.match(final.name))
        self.assertEqual(final.parent, self.dest)
        self.assertEqual(
            sorted(p.name for p in final.iterdir()),
            ["db.sqlite3", "manifest.json", "media", "private_media"],
        )
        self.assertEqual((final / "private_media" / "front.png").read_bytes()[:4], b"\x89PNG")
        self.assertTrue((final / "private_media" / "sub" / "back.png").is_file())
        self.assertTrue((final / "media" / "mockup.jpg").is_file())

    def test_env_logs_and_unrelated_files_are_never_copied(self):
        # Also plant forbidden names inside a media folder.
        (self.source / "private_media" / ".env").write_text(SECRET, encoding="utf-8")
        (self.source / "private_media" / "debug.log").write_text("x", encoding="utf-8")
        final = self.run_backup()
        names = {p.name for p in final.rglob("*")}
        for forbidden in (".env", "waitress.log", "debug.log",
                          "db-before-0009.sqlite3", "notes.txt"):
            self.assertNotIn(forbidden, names)
        for path in final.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"sk_live_not_a_real_key", path.read_bytes())
        self.assertEqual(backup.verify_backup(final, log=quiet), [])

    def test_integrity_and_manifest_are_right(self):
        final = self.run_backup()
        manifest = self.manifest_of(final)
        db = manifest["database"]
        self.assertEqual(db["integrity_check"], "ok")
        self.assertEqual(db["tables"]["shop_order"], 3)
        self.assertEqual(db["tables"]["shop_listing"], 2)
        self.assertEqual(db["tables"]["shop_design"], 4)
        self.assertEqual(db["sha256"], backup._sha256_file(final / "db.sqlite3"))
        conn = sqlite3.connect(str(final / "db.sqlite3"))
        self.assertEqual(conn.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM shop_order").fetchone()[0], 3)
        conn.close()
        pm = manifest["folders"]["private_media"]
        self.assertEqual(pm["file_count"], 2)
        self.assertEqual(pm["total_bytes"], 4 + 5000 + 4 + 300)
        self.assertEqual(sorted(pm["files"]), ["front.png", "sub/back.png"])
        media = manifest["folders"]["media"]
        self.assertEqual((media["file_count"], media["total_bytes"]), (1, 300))

    def test_the_source_is_never_modified(self):
        before = self.snapshot(self.source)
        self.run_backup()
        self.assertEqual(self.snapshot(self.source), before)

    def test_missing_or_empty_private_media_and_no_media_folder(self):
        import shutil
        shutil.rmtree(self.source / "private_media")
        shutil.rmtree(self.source / "media")
        final = self.run_backup()
        self.assertTrue((final / "private_media").is_dir())
        self.assertFalse((final / "media").exists())
        manifest = self.manifest_of(final)
        self.assertEqual(manifest["folders"]["private_media"]["file_count"], 0)
        self.assertFalse(manifest["folders"]["media"]["present"])
        self.assertEqual(backup.verify_backup(final, log=quiet), [])

        (self.source / "private_media").mkdir()  # present but empty
        second = self.run_backup(now=datetime.datetime(2030, 1, 1, 3, 0, 0))
        self.assertEqual(self.manifest_of(second)["folders"]["private_media"]["file_count"], 0)
        self.assertEqual(backup.verify_backup(second, log=quiet), [])

    def test_running_twice_in_the_same_second_makes_two_backups(self):
        moment = datetime.datetime(2031, 5, 6, 7, 8, 9)
        first = self.run_backup(now=moment)
        second = self.run_backup(now=moment)
        self.assertNotEqual(first, second)
        self.assertTrue(first.is_dir() and second.is_dir())
        self.assertEqual(first.name, "2031-05-06_070809")
        self.assertEqual(len(backup.list_backups(self.dest)), 2)
        self.assertEqual(backup.verify_backup(first, log=quiet), [])
        self.assertEqual(backup.verify_backup(second, log=quiet), [])

    def test_dest_inside_a_media_folder_is_refused(self):
        with self.assertRaises(backup.BackupError):
            backup.make_backup(self.source, self.source / "private_media" / "backups", log=quiet)


class LiveDatabaseTests(BackupTestCase):
    def test_backup_while_a_writer_has_the_database_open(self):
        writer = sqlite3.connect(str(self.source / "db.sqlite3"), timeout=10)
        try:
            writer.execute("BEGIN")
            writer.execute("INSERT INTO shop_order (email, total) VALUES ('pending@example.com', 1)")
            final = self.run_backup()  # the uncommitted order must not appear
            self.assertEqual(self.manifest_of(final)["database"]["tables"]["shop_order"], 3)
            writer.commit()
        finally:
            writer.close()
        second = self.run_backup(now=datetime.datetime(2032, 1, 1, 0, 0, 0))
        self.assertEqual(self.manifest_of(second)["database"]["tables"]["shop_order"], 4)
        self.assertEqual(backup.verify_backup(final, log=quiet), [])
        self.assertEqual(backup.verify_backup(second, log=quiet), [])

    def test_wal_database_with_unflushed_writes_is_captured(self):
        # The case a plain file copy of db.sqlite3 gets wrong: recent commits
        # still live in the -wal file while the app keeps the database open.
        (self.source / "db.sqlite3").unlink()
        make_database(self.source / "db.sqlite3", wal=True)
        writer = sqlite3.connect(str(self.source / "db.sqlite3"), timeout=10)
        try:
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute("INSERT INTO shop_order (email, total) VALUES ('wal@example.com', 5)")
            writer.commit()
            final = self.run_backup()
        finally:
            writer.close()
        self.assertEqual(self.manifest_of(final)["database"]["tables"]["shop_order"], 4)
        self.assertEqual(backup.verify_backup(final, log=quiet), [])


class RetentionTests(BackupTestCase):
    def test_keeps_the_newest_n_and_only_deletes_timestamped_folders(self):
        self.dest.mkdir()
        # Not backups: must survive retention untouched.
        (self.dest / "keep-me").mkdir()
        (self.dest / "keep-me" / "precious.txt").write_text("x", encoding="utf-8")
        (self.dest / "2026-1-1").mkdir()
        (self.dest / "2026-01-01_120000.zip").write_text("x", encoding="utf-8")
        (self.dest / "backup.log").write_text("x", encoding="utf-8")
        base = datetime.datetime(2030, 3, 1, 3, 0, 0)
        made = [
            self.run_backup(keep=3, now=base + datetime.timedelta(days=i)) for i in range(6)
        ]
        remaining = [p.name for p in backup.list_backups(self.dest)]
        self.assertEqual(remaining, [p.name for p in made[-3:]])
        for survivor in ("keep-me", "2026-1-1", "2026-01-01_120000.zip", "backup.log"):
            self.assertTrue((self.dest / survivor).exists(), survivor)
        self.assertTrue((self.dest / "keep-me" / "precious.txt").is_file())

    def test_default_keep_is_fourteen(self):
        self.assertEqual(backup.DEFAULT_KEEP, 14)
        self.assertEqual(backup.build_parser().parse_args([]).keep, 14)

    def test_keep_must_be_positive(self):
        with self.assertRaises(backup.BackupError):
            self.run_backup(keep=0)


class FailureTests(BackupTestCase):
    def leftovers(self):
        return [p.name for p in self.dest.iterdir() if p.name.startswith(".partial-")]

    def test_corrupt_source_exits_nonzero_and_keeps_old_backups(self):
        old = self.run_backup(now=datetime.datetime(2029, 1, 1, 3, 0, 0))
        (self.source / "db.sqlite3").write_bytes(b"this is not a sqlite database" * 100)
        result = self.run_cli("--source", self.source, "--dest", self.dest, "--keep", 1)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERROR", result.stdout)
        self.assertTrue(old.is_dir())
        self.assertEqual(backup.verify_backup(old, log=quiet), [])
        self.assertEqual([p.name for p in backup.list_backups(self.dest)], [old.name])
        self.assertEqual(self.leftovers(), [])

    def test_damaged_pages_fail_integrity_and_do_not_replace_good_backups(self):
        # A bigger database so there are interior pages to damage.
        (self.source / "db.sqlite3").unlink()
        make_database(self.source / "db.sqlite3", orders=3000)
        old = self.run_backup(now=datetime.datetime(2029, 1, 1, 3, 0, 0))
        path = self.source / "db.sqlite3"
        data = bytearray(path.read_bytes())
        for offset in range(8192, min(len(data), 8192 * 6), 97):
            data[offset] = (data[offset] + 77) % 256
        path.write_bytes(bytes(data))
        with self.assertRaises(backup.BackupError):
            self.run_backup(keep=1)
        self.assertEqual([p.name for p in backup.list_backups(self.dest)], [old.name])
        self.assertEqual(self.leftovers(), [])

    def test_missing_source_database_fails(self):
        (self.source / "db.sqlite3").unlink()
        result = self.run_cli("--source", self.source, "--dest", self.dest)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(backup.list_backups(self.dest), [])

    def test_failure_during_copy_cleans_up_and_keeps_old_backups(self):
        old = self.run_backup(now=datetime.datetime(2029, 1, 1, 3, 0, 0))
        with mock.patch.object(backup, "_copy_folder", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.run_backup(keep=1)
        self.assertEqual([p.name for p in backup.list_backups(self.dest)], [old.name])
        self.assertEqual(self.leftovers(), [])

    def test_a_good_run_exits_zero(self):
        result = self.run_cli("--source", self.source, "--dest", self.dest)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(backup.list_backups(self.dest)), 1)
        self.assertTrue((self.dest / "backup.log").is_file())
        self.assertNotIn("buyer0@example.com", result.stdout)


class VerifyAndRestoreTests(BackupTestCase):
    def test_verify_passes_on_a_good_backup(self):
        final = self.run_backup()
        self.assertEqual(backup.verify_backup(final, log=quiet), [])
        result = self.run_cli("--verify", final)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)

    def test_verify_defaults_to_the_newest_backup(self):
        self.run_backup(now=datetime.datetime(2030, 1, 1, 3, 0, 0))
        newest = self.run_backup(now=datetime.datetime(2030, 1, 2, 3, 0, 0))
        result = self.run_cli("--verify", "--source", self.source, "--dest", self.dest)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(newest.name, result.stdout)

    def test_verify_fails_when_the_database_is_tampered_with(self):
        final = self.run_backup()
        conn = sqlite3.connect(str(final / "db.sqlite3"))
        conn.execute("DELETE FROM shop_order")
        conn.commit()
        conn.close()
        problems = backup.verify_backup(final, log=quiet)
        self.assertTrue(problems)
        result = self.run_cli("--verify", final)
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL", result.stdout)

    def test_verify_fails_when_a_row_is_missing_but_the_file_checksum_is_forged(self):
        final = self.run_backup()
        conn = sqlite3.connect(str(final / "db.sqlite3"))
        conn.execute("DELETE FROM shop_order WHERE id = 1")
        conn.commit()
        conn.close()
        manifest = self.manifest_of(final)
        manifest["database"]["sha256"] = backup._sha256_file(final / "db.sqlite3")
        (final / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        problems = backup.verify_backup(final, log=quiet)
        self.assertTrue(any("shop_order" in p and "rows" in p for p in problems), problems)

    def test_verify_fails_on_a_changed_or_missing_artwork_file(self):
        final = self.run_backup()
        target = final / "private_media" / "front.png"
        original = target.read_bytes()
        target.write_bytes(original[:-1] + b"Z")  # same size, different content
        self.assertTrue(any("front.png" in p for p in backup.verify_backup(final, log=quiet)))
        target.write_bytes(original)
        self.assertEqual(backup.verify_backup(final, log=quiet), [])
        target.unlink()
        problems = backup.verify_backup(final, log=quiet)
        self.assertTrue(any("front.png" in p and "missing" in p for p in problems), problems)

    def test_verify_fails_on_a_corrupted_database_file(self):
        final = self.run_backup()
        with open(final / "db.sqlite3", "r+b") as handle:
            handle.seek(0)
            handle.write(b"garbage-header!!")
        self.assertTrue(backup.verify_backup(final, log=quiet))

    def test_verify_fails_if_an_env_file_has_been_added_to_the_backup(self):
        final = self.run_backup()
        (final / ".env").write_text(SECRET, encoding="utf-8")
        self.assertTrue(any(".env" in p for p in backup.verify_backup(final, log=quiet)))
        (final / ".env").unlink()
        (final / "private_media" / ".env").write_text(SECRET, encoding="utf-8")
        self.assertTrue(any(".env" in p for p in backup.verify_backup(final, log=quiet)))

    def test_verify_fails_without_a_manifest_or_folder(self):
        final = self.run_backup()
        (final / "manifest.json").unlink()
        self.assertTrue(backup.verify_backup(final, log=quiet))
        self.assertTrue(backup.verify_backup(self.tmp / "nope", log=quiet))

    def test_verify_leaves_no_temp_folders_and_does_not_touch_the_backup(self):
        final = self.run_backup()
        before = self.snapshot(final)
        scratch_root = Path(tempfile.gettempdir())
        existing = {p.name for p in scratch_root.glob("tcweb-restore-check-*")}
        backup.verify_backup(final, log=quiet)
        self.assertEqual(self.snapshot(final), before)
        self.assertEqual({p.name for p in scratch_root.glob("tcweb-restore-check-*")}, existing)

    def test_restore_refuses_to_overwrite_an_existing_database(self):
        final = self.run_backup()
        live = self.tmp / "live"
        live.mkdir()
        make_database(live / "db.sqlite3", orders=99)
        before = backup._sha256_file(live / "db.sqlite3")
        with self.assertRaises(backup.RestoreRefused):
            backup.restore_backup(final, live)
        self.assertEqual(backup._sha256_file(live / "db.sqlite3"), before)
        # ...and via the command line.
        result = self.run_cli("--restore-to", live, "--from", final)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(backup._sha256_file(live / "db.sqlite3"), before)

    def test_restore_refuses_a_non_empty_folder_and_a_file(self):
        final = self.run_backup()
        busy = self.tmp / "busy"
        busy.mkdir()
        (busy / "something.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(backup.RestoreRefused):
            backup.restore_backup(final, busy)
        afile = self.tmp / "afile"
        afile.write_text("x", encoding="utf-8")
        with self.assertRaises(backup.RestoreRefused):
            backup.restore_backup(final, afile)
        with self.assertRaises(backup.RestoreRefused):
            backup.restore_backup(final, final / "inside")

    def test_restore_into_a_new_folder_reproduces_the_data(self):
        final = self.run_backup()
        target = self.tmp / "restored"
        backup.restore_backup(final, target)
        integrity, tables = backup.inspect_database(target / "db.sqlite3")
        self.assertEqual(integrity, "ok")
        self.assertEqual(tables["shop_order"], 3)
        self.assertEqual((target / "private_media" / "front.png").read_bytes(),
                         (self.source / "private_media" / "front.png").read_bytes())
        self.assertFalse((target / ".env").exists())
