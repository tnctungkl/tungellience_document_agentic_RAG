from __future__ import annotations

import shutil
from collections.abc import Callable, Iterable
from pathlib import Path
from uuid import uuid4


def publish_artifacts_atomically(
    replacements: Iterable[tuple[Path, Path]],
    managed_destinations: Iterable[Path],
    backup_parent: Path,
    after_publish: Callable[[], None] | None = None,
) -> None:
    """Publish a group of generated files and restore the previous set on failure.

    All paths should be on the same filesystem so ``Path.replace`` remains atomic
    for each individual file. This provides rollback across the managed file set;
    it is not a filesystem-wide transaction against sudden power loss.
    """
    replacement_items = list(replacements)
    destinations = list(dict.fromkeys(managed_destinations))
    backup_root = backup_parent / f".artifact-backup-{uuid4().hex}"
    backup_root.mkdir(parents=True, exist_ok=False)
    backups: list[tuple[Path, Path]] = []
    published: list[Path] = []

    try:
        # Move the currently published artifact set aside before installing anything.
        for index, destination in enumerate(destinations):
            if destination.exists() or destination.is_symlink():
                backup = backup_root / f"{index:04d}-{destination.name}"
                destination.replace(backup)
                backups.append((destination, backup))

        # Destinations not present in replacements are intentionally removed as stale artifacts.
        for source, destination in replacement_items:
            if not source.is_file() or source.is_symlink():
                raise OSError(f"staged artifact is missing or invalid: {source.name}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.replace(destination)
            published.append(destination)

        if after_publish is not None:
            after_publish()
    except BaseException:
        for destination in reversed(published):
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
        for destination, backup in reversed(backups):
            try:
                if backup.exists() or backup.is_symlink():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    backup.replace(destination)
            except OSError:
                # Preserve the original exception; callers should also inspect server logs.
                pass
        raise
    finally:
        shutil.rmtree(backup_root, ignore_errors=True)
