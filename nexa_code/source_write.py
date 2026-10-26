"""Recoverable source-file installation, separate from immutable SourceSync records."""

from __future__ import annotations

import os
import re
import stat
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from src.open_programs.model import FrozenModel, ProgramError, content_digest
from src.open_programs.store import ProgramStore


class SourceWriteIntent(FrozenModel):
    sync_id: str
    path: str
    directory: str
    parent_device: int
    parent_inode: int
    base_digest: str
    source_digest: str
    phase: Literal["prepared", "staged", "installed", "interrupted", "conflict", "complete"] = "prepared"


def read_source(path: Path) -> str:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return handle.read()
    except FileNotFoundError as error:
        raise ProgramError("source_recovery_required", "Source is missing; inspect its pending source recovery paths before restoring the file") from error


def _read(directory: int, name: str) -> tuple[str, os.stat_result] | None:
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ProgramError("source_conflict", "Source recovery requires regular files") from error
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ProgramError("source_conflict", "Source recovery requires regular files")
        try:
            text = handle.read().decode("utf-8")
        except UnicodeDecodeError as error:
            raise ProgramError("source_conflict", "Source recovery found a non-UTF-8 edit; all files are retained") from error
        return content_digest(text), info


class SourceWriter:
    def __init__(self, store: ProgramStore, path: Path, key: str) -> None:
        self.store, self.path = store, path
        self.prefix = "code.source-write:" + content_digest(key) + ":"

    def records(self) -> list[SourceWriteIntent]:
        return self.store.references(self.prefix, SourceWriteIntent)

    def _save(self, record: SourceWriteIntent, phase: str) -> SourceWriteIntent:
        updated = SourceWriteIntent.model_validate({**record.model_dump(), "phase": phase})
        if updated != record:
            self.store.set_reference(self.prefix + record.directory, record.digest, updated)
        return updated

    @contextmanager
    def _parent(self, record: SourceWriteIntent | None = None) -> Generator[int, None, None]:
        descriptor = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(descriptor)
            if record and (
                record.path != str(self.path)
                or not re.fullmatch(r"\.nexa-intent-[a-f0-9]{32}", record.directory)
                or (info.st_dev, info.st_ino) != (record.parent_device, record.parent_inode)
            ):
                raise ProgramError("source_conflict", "Source recovery directory identity changed")
            yield descriptor
        finally:
            os.close(descriptor)

    def recover(self) -> None:
        for record in self.records():
            if record.phase != "complete":
                self._save(record, self._recover(record))

    def _recover(self, record: SourceWriteIntent) -> str:
        try:
            with self._parent(record) as parent:
                try:
                    directory = os.open(record.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                except FileNotFoundError:
                    return "interrupted" if _read(parent, self.path.name) else "conflict"
                try:
                    return self._recover_files(parent, directory, record)
                finally:
                    os.close(directory)
        except (OSError, ProgramError):
            # A conflicting path must remain available in status; execution checks the persisted conflict.
            return "conflict"

    def _recover_files(self, parent: int, directory: int, record: SourceWriteIntent) -> str:
        current, original = _read(parent, self.path.name), _read(directory, "original")
        if current is None and original:
            try:
                os.link("original", self.path.name, src_dir_fd=directory, dst_dir_fd=parent, follow_symlinks=False)
                os.fsync(parent)
            except FileExistsError:
                return "conflict"
            current = _read(parent, self.path.name)
        if original and original[0] != record.base_digest:
            return "conflict"
        if current is None or current[0] not in {record.base_digest, record.source_digest}:
            return "conflict"
        if current[0] == record.source_digest:
            self._clean_temporary(parent, directory, record)
            return "installed"
        return "interrupted"

    def _clean_temporary(self, parent: int, directory: int, record: SourceWriteIntent) -> None:
        temporary, current = _read(directory, "replacement"), _read(parent, self.path.name)
        if temporary is None:
            return
        if temporary[0] != record.source_digest or (temporary[1].st_nlink > 1 and (current is None or temporary[1].st_ino != current[1].st_ino)):
            raise ProgramError("source_conflict", "Temporary source was edited; its recovery path is retained")
        os.unlink("replacement", dir_fd=directory)
        os.fsync(directory)

    def write(self, sync_id: str, base: str, source: str) -> None:
        if any(
            record.base_digest == content_digest(base) and record.source_digest == content_digest(source) and record.phase == "conflict"
            for record in self.records()
        ):
            raise ProgramError("source_conflict", "Concurrent source edits are retained; inspect source_recovery paths and reconcile before syncing")
        with self._parent() as parent:
            before = _read(parent, self.path.name)
            if before and before[0] == content_digest(source):
                return
            if before is None or before[0] != content_digest(base):
                raise ProgramError("source_conflict", "Source changed; the pending intent diff remains available")
            info = os.fstat(parent)
            record = SourceWriteIntent(
                sync_id=sync_id,
                path=str(self.path),
                directory=".nexa-intent-" + uuid.uuid4().hex,
                parent_device=info.st_dev,
                parent_inode=info.st_ino,
                base_digest=content_digest(base),
                source_digest=content_digest(source),
            )
            self.store.set_reference(self.prefix + record.directory, None, record)
            self._install(parent, record, source, stat.S_IMODE(before[1].st_mode))

    def _install(self, parent: int, record: SourceWriteIntent, source: str, mode: int) -> None:
        os.mkdir(record.directory, 0o700, dir_fd=parent)
        os.fsync(parent)
        directory = os.open(record.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            descriptor = os.open("replacement", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(source.encode("utf-8"))
                os.fchmod(handle.fileno(), mode)
                handle.flush()
                os.fsync(handle.fileno())
            os.fsync(directory)
            record = self._save(record, "staged")
            current = _read(parent, self.path.name)
            if current is None or current[0] != record.base_digest:
                raise ProgramError("source_conflict", "Source changed while staging the intent diff")
            os.rename(self.path.name, "original", src_dir_fd=parent, dst_dir_fd=directory)
            os.fsync(directory)
            os.fsync(parent)
            self._verify_original(directory, record)
            try:
                os.link("replacement", self.path.name, src_dir_fd=directory, dst_dir_fd=parent, follow_symlinks=False)
            except FileExistsError as error:
                raise ProgramError("source_conflict", "Another writer recreated the source; both files are retained") from error
            os.fsync(parent)
            self._verify_original(directory, record)
            record = self._save(record, "installed")
            self._clean_temporary(parent, directory, record)
        except BaseException:
            self._save(record, self._recover(record))
            raise
        finally:
            os.close(directory)

    def _verify_original(self, directory: int, record: SourceWriteIntent) -> None:
        original = _read(directory, "original")
        if original is None or original[0] != record.base_digest:
            raise ProgramError("source_conflict", "Concurrent source edit retained at " + str(self.path.parent / record.directory / "original"))

    def complete(self, base_digest: str, source_digest: str) -> None:
        # A committed revision can reach completion without another write, and an old editor fd may have changed the retained inode.
        records = [
            self._save(record, self._recover(record))
            for record in self.records()
            if record.base_digest == base_digest and record.source_digest == source_digest
        ]
        if any(record.phase == "conflict" for record in records):
            raise ProgramError("source_conflict", "Concurrent source edits are retained; inspect source_recovery paths and reconcile before syncing")
        for record in records:
            self._save(record, "complete")

    def views(self) -> list[dict[str, str]]:
        return [
            {
                "sync_id": record.sync_id,
                "state": record.phase,
                "original_path": str(self.path.parent / record.directory / "original"),
                "temporary_path": str(self.path.parent / record.directory / "replacement"),
            }
            for record in self.records()
        ]
