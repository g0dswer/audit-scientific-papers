#!/usr/bin/env python3
"""Install a consented stable update with validation and rollback support."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import stat
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable

import check_for_update as update_check

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows uses msvcrt below.
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX uses fcntl above.
    msvcrt = None


MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_EXTRACTED_BYTES = 75 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 2_000
STATE_FILE = ".update-state.json"
_LINK_RE = re.compile(r"\]\(([^)]+)\)")


class UpdateInstallError(RuntimeError):
    """Raised when an update cannot be safely installed."""


def archive_url(commit: str) -> str:
    try:
        commit = update_check._validated_sha(commit)
    except update_check.UpdateCheckError as exc:
        raise UpdateInstallError(str(exc)) from exc
    return (
        "https://github.com/g0dswer/audit-scientific-papers/"
        f"archive/{commit}.tar.gz"
    )


def download_archive(commit: str, timeout: float = 30.0) -> bytes:
    """Download the exact release commit resolved before user consent."""

    url = archive_url(commit)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"{update_check.SKILL_NAME}-updater/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            final = urllib.parse.urlparse(response.geturl())
            if final.scheme != "https" or final.hostname not in {
                "github.com",
                "codeload.github.com",
            }:
                raise UpdateInstallError("archive request redirected outside GitHub")
            accepted_paths = {
                f"/g0dswer/audit-scientific-papers/archive/{commit}.tar.gz",
                f"/g0dswer/audit-scientific-papers/tar.gz/{commit}",
            }
            if final.path not in accepted_paths:
                raise UpdateInstallError("archive request redirected outside the repository")
            length = response.headers.get("Content-Length")
            expected_length = int(length) if length is not None else None
            if expected_length is not None and expected_length > MAX_ARCHIVE_BYTES:
                raise UpdateInstallError("release archive is unexpectedly large")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    raise UpdateInstallError("release archive is unexpectedly large")
                chunks.append(chunk)
            if expected_length is not None and total != expected_length:
                raise UpdateInstallError(
                    "release archive ended before its declared content length"
                )
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise UpdateInstallError(
            f"cannot download stable release commit {commit}: {exc}"
        ) from exc
    return b"".join(chunks)


def _safe_member_parts(member: tarfile.TarInfo) -> tuple[str, ...]:
    if "\\" in member.name:
        raise UpdateInstallError("release archive contains a backslash path")
    path = PurePosixPath(member.name)
    parts = tuple(part for part in path.parts if part not in {"", "."})
    if not parts or path.is_absolute() or ".." in parts or ":" in parts[0]:
        raise UpdateInstallError("release archive contains an unsafe path")
    if member.issym() or member.islnk():
        raise UpdateInstallError("release archive contains a link")
    if not (member.isdir() or member.isfile()):
        raise UpdateInstallError("release archive contains an unsupported entry type")
    if member.size < 0:
        raise UpdateInstallError("release archive contains an invalid file size")
    return parts


def _copy_exact(source: Any, output: Any, expected_size: int) -> None:
    """Copy exactly one declared tar member and reject an early end of stream."""

    remaining = expected_size
    while remaining:
        chunk = source.read(min(64 * 1024, remaining))
        if not chunk:
            raise UpdateInstallError("release archive contains a truncated file")
        output.write(chunk)
        remaining -= len(chunk)


def safe_extract_archive(data: bytes, destination: Path) -> Path:
    """Extract regular files only and return the archive's single top-level root."""

    if not destination.is_dir() or any(destination.iterdir()):
        raise UpdateInstallError("archive destination must be an empty directory")
    destination_resolved = destination.resolve()
    member_count = 0
    total = 0
    top_level: str | None = None
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r|gz") as archive:
            for member in archive:
                member_count += 1
                if member_count > MAX_ARCHIVE_MEMBERS:
                    raise UpdateInstallError("release archive has too many entries")
                parts = _safe_member_parts(member)
                if top_level is None:
                    top_level = parts[0]
                elif parts[0] != top_level:
                    raise UpdateInstallError(
                        "release archive must contain one top-level directory"
                    )
                total += member.size
                if total > MAX_EXTRACTED_BYTES:
                    raise UpdateInstallError(
                        "release archive expands beyond the size limit"
                    )
                target = destination.joinpath(*parts)
                target_resolved = target.resolve(strict=False)
                if destination_resolved not in target_resolved.parents:
                    raise UpdateInstallError("release archive escaped the destination")
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise UpdateInstallError("release archive file could not be read")
                with source, target.open("wb") as output:
                    _copy_exact(source, output, member.size)
                target.chmod(member.mode & 0o755)
    except UpdateInstallError:
        raise
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise UpdateInstallError(f"release archive is invalid: {exc}") from exc
    if member_count == 0 or top_level is None:
        raise UpdateInstallError("release archive is empty")
    return destination / top_level


def _read_json(path: Path, *, maximum: int = 64 * 1024) -> Any:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise UpdateInstallError(f"cannot read {path.name}: {exc}") from exc
    if len(raw) > maximum:
        raise UpdateInstallError(f"{path.name} is unexpectedly large")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateInstallError(f"{path.name} is not valid UTF-8 JSON: {exc}") from exc


def _validate_skill_links(candidate: Path, skill_text: str) -> None:
    for target_text in _LINK_RE.findall(skill_text):
        target_text = target_text.split("#", 1)[0].strip()
        if not target_text or "://" in target_text or target_text.startswith(("#", "mailto:")):
            continue
        target = candidate / target_text
        try:
            target.resolve(strict=True).relative_to(candidate.resolve())
        except (OSError, ValueError) as exc:
            raise UpdateInstallError(
                f"SKILL.md references a missing or unsafe path: {target_text}"
            ) from exc


def validate_candidate(candidate: Path, expected_manifest: dict[str, Any]) -> None:
    """Validate release identity, entrypoint, references, and updater presence."""

    if not candidate.is_dir() or candidate.is_symlink():
        raise UpdateInstallError("release candidate is not a regular directory")
    for path in candidate.rglob("*"):
        if path.is_symlink():
            raise UpdateInstallError("release candidate contains a symbolic link")
        if not (path.is_file() or path.is_dir()):
            raise UpdateInstallError("release candidate contains a special file")

    try:
        version = update_check.read_local_version(candidate)
    except update_check.UpdateCheckError as exc:
        raise UpdateInstallError(str(exc)) from exc
    expected = update_check.validate_manifest(expected_manifest)
    if version != expected["version"]:
        raise UpdateInstallError("candidate VERSION does not match the stable manifest")
    try:
        candidate_manifest = update_check.validate_manifest(
            _read_json(candidate / "skill-manifest.json")
        )
    except update_check.UpdateCheckError as exc:
        raise UpdateInstallError(str(exc)) from exc
    if candidate_manifest != expected:
        raise UpdateInstallError("candidate manifest differs from the stable manifest")

    skill_path = candidate / "SKILL.md"
    try:
        skill_text = skill_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UpdateInstallError(f"cannot read candidate SKILL.md: {exc}") from exc
    lines = skill_text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise UpdateInstallError("candidate SKILL.md has no YAML frontmatter")
    try:
        frontmatter_end = next(
            index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration as exc:
        raise UpdateInstallError("candidate SKILL.md frontmatter is not closed") from exc
    frontmatter = "\n".join(lines[1:frontmatter_end])
    if not re.search(
        rf"(?m)^name:\s*{re.escape(update_check.SKILL_NAME)}\s*$", frontmatter
    ):
        raise UpdateInstallError("candidate SKILL.md names a different skill")
    _validate_skill_links(candidate, skill_text)
    for relative in (
        "scripts/check_for_update.py",
        "scripts/update_skill.py",
        "scripts/test_updates.py",
    ):
        if not (candidate / relative).is_file():
            raise UpdateInstallError(f"candidate is missing {relative}")


def validate_managed_skill_root(skill_root: Path) -> Path:
    """Refuse to replace symlinks, unexpected paths, or developer Git checkouts."""

    expanded = skill_root.expanduser()
    if expanded.is_symlink():
        raise UpdateInstallError("the installed skill root cannot be a symbolic link")
    try:
        resolved = expanded.resolve(strict=True)
    except OSError as exc:
        raise UpdateInstallError(f"cannot resolve installed skill root: {exc}") from exc
    if not resolved.is_dir() or resolved.name != update_check.SKILL_NAME:
        raise UpdateInstallError("installed skill root has an unexpected name or type")
    if (resolved / ".git").exists():
        raise UpdateInstallError(
            "automatic replacement is disabled for Git checkouts; update that checkout "
            "with Git or reinstall a release archive"
        )
    update_check.read_local_version(resolved)
    return resolved


def validate_retained_backup(backup: Path, expected_version: str) -> None:
    """Validate the retained package identity before using it for recovery."""

    if backup.is_symlink() or not backup.is_dir():
        raise UpdateInstallError("retained backup is not a regular directory")
    try:
        actual_version = update_check.read_local_version(backup)
    except update_check.UpdateCheckError as exc:
        raise UpdateInstallError(f"retained backup is invalid: {exc}") from exc
    if actual_version != expected_version:
        raise UpdateInstallError("retained backup VERSION differs from recovery state")
    try:
        backup_manifest = update_check.validate_manifest(
            _read_json(backup / "skill-manifest.json")
        )
        validate_candidate(backup, backup_manifest)
    except (UpdateInstallError, update_check.UpdateCheckError) as exc:
        raise UpdateInstallError(f"retained backup is invalid: {exc}") from exc


def tree_digest(root: Path) -> str:
    """Hash validated relative paths and file bytes for rollback integrity."""

    digest = hashlib.sha256()
    paths = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
    for path in paths:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise UpdateInstallError(
                "cannot hash a backup containing links or special files"
            )
        digest.update(b"d" if path.is_dir() else b"f")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        if path.is_file():
            try:
                with path.open("rb") as handle:
                    while True:
                        chunk = handle.read(64 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
            except OSError as exc:
                raise UpdateInstallError(
                    f"cannot hash retained backup: {exc}"
                ) from exc
    return digest.hexdigest()


def _unique_sibling(parent: Path, prefix: str) -> Path:
    for _ in range(20):
        candidate = parent / f"{prefix}{uuid.uuid4().hex[:10]}"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise UpdateInstallError("could not allocate a unique update path")


def _safe_remove_tree(path: Path, parent: Path, prefix: str) -> None:
    parent_resolved = parent.resolve(strict=True)
    path_resolved = path.resolve(strict=False)
    if path_resolved.parent != parent_resolved or not path.name.startswith(prefix):
        raise UpdateInstallError("refused to clean an unexpected update path")
    if path.is_symlink():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _read_lock_metadata(descriptor: int) -> dict[str, Any] | None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    raw = os.read(descriptor, 4_098)
    if raw.startswith(b"\0"):
        raw = raw[1:]
    if len(raw) > 4_096:
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_lock_metadata(descriptor: int, payload: dict[str, Any]) -> None:
    metadata = json.dumps(payload, sort_keys=True).encode("utf-8")
    if len(metadata) > 4_096:
        raise UpdateInstallError("update lock metadata is unexpectedly large")
    os.ftruncate(descriptor, 1)
    os.lseek(descriptor, 0, os.SEEK_SET)
    os.write(descriptor, b"\0")
    os.lseek(descriptor, 1, os.SEEK_SET)
    view = memoryview(metadata)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise UpdateInstallError("could not write update lock metadata")
        view = view[written:]
    os.fsync(descriptor)


@contextmanager
def exclusive_update_lock(parent: Path):
    """Serialize mutation with a kernel lock that is released on process exit."""

    lock = parent / f".{update_check.SKILL_NAME}.update.lock"
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock, flags, 0o600)
    except OSError as exc:
        raise UpdateInstallError(
            f"cannot open the update lock in {parent}: {exc}"
        ) from exc
    locked = False
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise UpdateInstallError("the update lock path is not a regular file")
        try:
            if fcntl is not None:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            elif msvcrt is not None:
                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"\0")
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:  # pragma: no cover - supported Python platforms provide one.
                raise UpdateInstallError("no supported operating-system lock is available")
        except (BlockingIOError, OSError) as exc:
            raise UpdateInstallError(
                f"another update or recovery is active; lock file: {lock}"
            ) from exc
        locked = True
        previous = _read_lock_metadata(descriptor)
        active = dict(previous) if previous is not None else {}
        active.update(
            {
                "lock_pid": os.getpid(),
                "lock_acquired_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        _write_lock_metadata(descriptor, active)
        yield descriptor, previous
    finally:
        if locked:
            try:
                if fcntl is not None:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                elif msvcrt is not None:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        os.close(descriptor)


def activate_candidate(
    candidate: Path,
    skill_root: Path,
    *,
    installed_version: str,
    available_version: str,
    expected_manifest: dict[str, Any],
) -> dict[str, str]:
    """Copy then atomically swap a validated candidate, restoring on swap failure."""

    root = validate_managed_skill_root(skill_root)
    parent = root.parent
    with exclusive_update_lock(parent) as lock_context:
        lock_descriptor, _ = lock_context
        root = validate_managed_skill_root(root)
        current_version = update_check.read_local_version(root)
        if current_version != installed_version:
            raise UpdateInstallError(
                "installed version changed after the update check; run the check again"
            )
        try:
            container = Path(
                tempfile.mkdtemp(
                    prefix=f".{update_check.SKILL_NAME}.stage-", dir=parent
                )
            )
        except OSError as exc:
            raise UpdateInstallError(
                f"cannot create a staging directory beside the installed skill: {exc}"
            ) from exc
        staged = container / update_check.SKILL_NAME
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = _unique_sibling(
            parent,
            f".{update_check.SKILL_NAME}.backup-{installed_version}-{timestamp}-",
        )
        bookkeeping_warning = None
        try:
            backup_digest = tree_digest(root)
            recovery_state = {
                "schema_version": 1,
                "phase": "prepared",
                "skill_root": str(root),
                "backup_path": str(backup),
                "backup_sha256": backup_digest,
                "previous_version": installed_version,
                "lock_pid": os.getpid(),
                "lock_acquired_at": datetime.now(timezone.utc).isoformat(),
            }
            _write_lock_metadata(lock_descriptor, recovery_state)
            shutil.copytree(candidate, staged, symlinks=True)
            validate_candidate(staged, expected_manifest)
            state = {
                "schema_version": 1,
                "previous_version": installed_version,
                "installed_version": available_version,
                "backup_path": str(backup),
                "backup_sha256": backup_digest,
                "installed_at": datetime.now(timezone.utc).isoformat(),
            }
            (staged / STATE_FILE).write_text(
                json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            os.replace(root, backup)
            try:
                os.replace(staged, root)
            except BaseException:
                os.replace(backup, root)
                raise
            recovery_state["phase"] = "activated"
            try:
                _write_lock_metadata(lock_descriptor, recovery_state)
            except (OSError, UpdateInstallError) as metadata_exc:
                bookkeeping_warning = (
                    "The update is active, but final lock metadata could not be marked "
                    f"activated: {metadata_exc}. The fsynced prepared recovery record "
                    "and installed rollback state remain available."
                )
        except BaseException as exc:
            if not root.exists() and backup.exists():
                try:
                    os.replace(backup, root)
                except OSError as restore_exc:
                    raise UpdateInstallError(
                        "update failed and automatic restore also failed; the original "
                        f"directory remains at {backup}: {restore_exc}"
                    ) from exc
            if isinstance(exc, UpdateInstallError):
                raise
            raise UpdateInstallError(f"could not activate update: {exc}") from exc
        finally:
            if container.exists():
                _safe_remove_tree(
                    container,
                    parent,
                    f".{update_check.SKILL_NAME}.stage-",
                )
    result = {
        "installed_path": str(root),
        "backup_path": str(backup),
        "previous_version": installed_version,
        "installed_version": available_version,
    }
    if bookkeeping_warning is not None:
        result["bookkeeping_warning"] = bookkeeping_warning
    return result


def rollback(skill_root: Path) -> dict[str, str]:
    """Restore the exact retained copy recorded by the latest managed update."""

    root = validate_managed_skill_root(skill_root)
    parent = root.parent.resolve(strict=True)
    with exclusive_update_lock(parent):
        return _rollback_locked(root, parent)


def recover_interrupted_activation(
    skill_root: Path, backup_path: Path
) -> dict[str, str]:
    """Restore an explicitly selected valid backup when the install root is absent."""

    requested_root = skill_root.expanduser().absolute()
    if (
        requested_root.name != update_check.SKILL_NAME
        or requested_root.is_symlink()
        or requested_root.exists()
    ):
        raise UpdateInstallError(
            "interruption recovery requires the expected missing skill directory"
        )
    try:
        parent = requested_root.parent.resolve(strict=True)
    except OSError as exc:
        raise UpdateInstallError(f"cannot resolve the skill parent directory: {exc}") from exc
    root = parent / update_check.SKILL_NAME
    if root.exists() or root.is_symlink():
        raise UpdateInstallError(
            "the canonical skill directory exists; inspect it before recovery"
        )
    backup_unresolved = backup_path.expanduser()
    if backup_unresolved.is_symlink():
        raise UpdateInstallError("recovery backup cannot be a symbolic link")
    try:
        backup = backup_unresolved.resolve(strict=True)
    except OSError as exc:
        raise UpdateInstallError(f"recovery backup is unavailable: {exc}") from exc
    expected_prefix = f".{update_check.SKILL_NAME}.backup-"
    if backup.parent != parent or not backup.name.startswith(expected_prefix):
        raise UpdateInstallError("recovery backup is outside the managed skill directory")
    try:
        version = update_check.read_local_version(backup)
    except update_check.UpdateCheckError as exc:
        raise UpdateInstallError(f"retained backup is invalid: {exc}") from exc
    validate_retained_backup(backup, version)
    with exclusive_update_lock(parent) as lock_context:
        lock_descriptor, recovery_state = lock_context
        if root.exists() or root.is_symlink():
            raise UpdateInstallError(
                "the skill directory reappeared; inspect it before attempting recovery"
            )
        validate_retained_backup(backup, version)
        if not isinstance(recovery_state, dict):
            raise UpdateInstallError(
                "the persistent lock has no validated interruption-recovery record"
            )
        expected_digest = recovery_state.get("backup_sha256")
        if (
            recovery_state.get("schema_version") != 1
            or recovery_state.get("phase") not in {"prepared", "activated"}
            or recovery_state.get("skill_root") != str(root)
            or recovery_state.get("backup_path") != str(backup)
            or recovery_state.get("previous_version") != version
            or not isinstance(expected_digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_digest)
            or tree_digest(backup) != expected_digest
        ):
            raise UpdateInstallError(
                "the selected backup does not match the interruption-recovery record"
            )
        try:
            os.replace(backup, root)
        except OSError as exc:
            raise UpdateInstallError(f"could not restore the retained backup: {exc}") from exc
        recovered_state = dict(recovery_state)
        recovered_state["phase"] = "recovered"
        recovered_state["lock_pid"] = os.getpid()
        recovered_state["lock_acquired_at"] = datetime.now(timezone.utc).isoformat()
        _write_lock_metadata(lock_descriptor, recovered_state)
    return {"restored_path": str(root), "restored_version": version}


def _rollback_locked(root: Path, parent: Path) -> dict[str, str]:
    root = validate_managed_skill_root(root)
    state = _read_json(root / STATE_FILE)
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise UpdateInstallError("update state is missing or invalid")
    previous_version = state.get("previous_version")
    installed_version = state.get("installed_version")
    if not isinstance(previous_version, str) or not isinstance(installed_version, str):
        raise UpdateInstallError("update state has invalid version fields")
    try:
        update_check.parse_version(previous_version)
        update_check.parse_version(installed_version)
    except update_check.UpdateCheckError as exc:
        raise UpdateInstallError("update state has invalid version fields") from exc
    backup_text = state.get("backup_path")
    if not isinstance(backup_text, str) or not backup_text:
        raise UpdateInstallError("update state has no backup path")
    backup_unresolved = Path(backup_text)
    if backup_unresolved.is_symlink():
        raise UpdateInstallError("recorded backup cannot be a symbolic link")
    try:
        backup = backup_unresolved.resolve(strict=True)
    except OSError as exc:
        raise UpdateInstallError(f"recorded backup is unavailable: {exc}") from exc
    expected_prefix = f".{update_check.SKILL_NAME}.backup-"
    if backup.parent != parent or not backup.name.startswith(expected_prefix) or not backup.is_dir():
        raise UpdateInstallError("recorded backup path is outside the managed skill directory")
    validate_retained_backup(backup, previous_version)
    backup_digest = state.get("backup_sha256")
    if (
        not isinstance(backup_digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", backup_digest)
        or tree_digest(backup) != backup_digest
    ):
        raise UpdateInstallError("retained backup content differs from recovery state")
    failed = _unique_sibling(
        parent,
        f".{update_check.SKILL_NAME}.rolled-back-"
        f"{installed_version}-",
    )
    os.replace(root, failed)
    try:
        os.replace(backup, root)
    except BaseException as exc:
        os.replace(failed, root)
        raise UpdateInstallError("rollback failed; the current version was restored") from exc
    return {
        "restored_path": str(root),
        "restored_version": previous_version,
        "replaced_version_path": str(failed),
    }


def perform_update(
    skill_root: Path,
    *,
    timeout: float = 30.0,
    manifest_loader: Callable[[], dict[str, Any]] | None = None,
    archive_loader: Callable[[str, float], bytes] = download_archive,
    approved_commit: str,
    approved_version: str,
) -> dict[str, Any]:
    """Download, validate, and activate one newer stable release."""

    root = validate_managed_skill_root(skill_root)
    installed = update_check.read_local_version(root)
    try:
        release = update_check.validate_release_info(
            manifest_loader() if manifest_loader else update_check.fetch_release_info(timeout)
        )
    except update_check.UpdateCheckError as exc:
        raise UpdateInstallError(str(exc)) from exc
    manifest = release["manifest"]
    if release["commit"] != approved_commit or manifest["version"] != approved_version:
        raise UpdateInstallError(
            "the stable release changed after consent; run the update check and ask again"
        )
    if update_check.compare_versions(installed, manifest["version"]) >= 0:
        raise UpdateInstallError("no newer stable version is available")
    if manifest["minimum_updater_protocol"] > update_check.UPDATER_PROTOCOL_VERSION:
        raise UpdateInstallError("this release requires a newer updater; reinstall manually")

    archive = archive_loader(release["commit"], timeout)
    with tempfile.TemporaryDirectory(prefix=f"{update_check.SKILL_NAME}-update-") as temp:
        extraction = Path(temp) / "extract"
        extraction.mkdir()
        candidate = safe_extract_archive(archive, extraction)
        validate_candidate(candidate, manifest)
        activation = activate_candidate(
            candidate,
            root,
            installed_version=installed,
            available_version=manifest["version"],
            expected_manifest=manifest,
        )
    return {
        "status": "updated",
        "tag": manifest["tag"],
        "commit": release["commit"],
        "release_url": release["release_url"],
        **activation,
    }


def _emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if payload.get("status") == "updated":
        print(
            f"Updated Audit Scientific Papers from {payload['previous_version']} "
            f"to {payload['installed_version']}."
        )
        print(f"Rollback copy: {payload['backup_path']}")
        if payload.get("bookkeeping_warning"):
            print(f"Warning: {payload['bookkeeping_warning']}")
        print("Reload SKILL.md before beginning the audit.")
    elif payload.get("status") == "rolled_back":
        print(f"Restored Audit Scientific Papers {payload['restored_version']}.")
        print(f"Replaced version retained at: {payload['replaced_version_path']}")
    elif payload.get("status") == "recovered":
        print(
            "Recovered Audit Scientific Papers "
            f"{payload['restored_version']} after an interrupted activation."
        )
    else:
        update_check._print_human(payload)


def installation_health(skill_root: Path) -> dict[str, Any]:
    """Report whether the original installed copy is still usable after an error."""

    try:
        expanded = skill_root.expanduser()
        if expanded.is_symlink():
            raise OSError("skill root is a symbolic link")
        root = expanded.resolve(strict=True)
        version = update_check.read_local_version(root)
        required = (
            root / "SKILL.md",
            root / "references" / "update-protocol.md",
            root / "scripts" / "check_for_update.py",
            root / "scripts" / "update_skill.py",
        )
        intact = root.is_dir() and root.name == update_check.SKILL_NAME
        for path in required:
            if path.is_symlink() or not path.is_file():
                intact = False
                break
            with path.open("rb") as handle:
                handle.read(1)
        if intact:
            for path in root.rglob("*"):
                if path.is_symlink() or not (path.is_file() or path.is_dir()):
                    intact = False
                    break
    except (OSError, UnicodeError, update_check.UpdateCheckError):
        return {"installation_intact": False, "continue_with_installed": False}
    return {
        "installation_intact": intact,
        "continue_with_installed": intact,
        "installed_version": version,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--confirm-update",
        action="store_true",
        help="confirm that the user approved installing the available stable update",
    )
    actions.add_argument(
        "--confirm-rollback",
        action="store_true",
        help="confirm that the user approved restoring the retained previous version",
    )
    actions.add_argument(
        "--confirm-recovery",
        action="store_true",
        help="confirm recovery of a missing install root from an exact retained backup",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--approved-commit")
    parser.add_argument("--approved-version")
    parser.add_argument("--recovery-backup", type=Path)
    parser.add_argument(
        "--skill-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.timeout > 300:
        parser.error("--timeout must be greater than 0 and at most 300")
    try:
        if args.confirm_rollback:
            payload = {"status": "rolled_back", **rollback(args.skill_root)}
        elif args.confirm_recovery:
            if args.recovery_backup is None:
                raise UpdateInstallError(
                    "--confirm-recovery requires --recovery-backup with the exact retained path"
                )
            payload = {
                "status": "recovered",
                **recover_interrupted_activation(
                    args.skill_root, args.recovery_backup
                ),
            }
        elif args.confirm_update:
            if not args.approved_commit or not args.approved_version:
                raise UpdateInstallError(
                    "--confirm-update requires --approved-commit and --approved-version "
                    "from the consented update check"
                )
            payload = perform_update(
                args.skill_root,
                timeout=args.timeout,
                approved_commit=args.approved_commit,
                approved_version=args.approved_version,
            )
        else:
            payload = update_check.check_for_update(
                args.skill_root.expanduser(),
                manifest_loader=lambda: update_check.fetch_release_info(
                    min(args.timeout, 60)
                ),
            )
        _emit(payload, args.json)
    except (OSError, UnicodeError, UpdateInstallError, update_check.UpdateCheckError) as exc:
        payload = {
            "status": "error",
            "message": str(exc),
            **installation_health(args.skill_root),
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Update not installed: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
