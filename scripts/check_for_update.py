#!/usr/bin/env python3
"""Check the trusted stable update manifest without changing local files."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable


SKILL_NAME = "audit-scientific-papers"
REPOSITORY = "g0dswer/audit-scientific-papers"
UPDATER_PROTOCOL_VERSION = 1
LATEST_RELEASE_URL = (
    "https://api.github.com/repos/g0dswer/audit-scientific-papers/releases/latest"
)
MAX_MANIFEST_BYTES = 64 * 1024
MAX_RELEASE_BYTES = 256 * 1024
_RELEASE_PATH = "/repos/g0dswer/audit-scientific-papers/releases/latest"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


class UpdateCheckError(RuntimeError):
    """Raised when local or remote update metadata is invalid."""


@dataclass(frozen=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...]


def parse_version(value: str) -> SemVer:
    """Parse the SemVer subset used by stable skill releases."""

    match = _SEMVER_RE.fullmatch(value.strip())
    if not match:
        raise UpdateCheckError(f"invalid semantic version: {value!r}")
    prerelease = tuple(match.group(4).split(".")) if match.group(4) else ()
    for identifier in prerelease:
        if identifier.isdigit() and len(identifier) > 1 and identifier.startswith("0"):
            raise UpdateCheckError(
                f"numeric prerelease identifiers cannot have leading zeroes: {value!r}"
            )
    return SemVer(
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        prerelease,
    )


def compare_versions(left: str, right: str) -> int:
    """Return -1, 0, or 1 using Semantic Versioning precedence."""

    a = parse_version(left)
    b = parse_version(right)
    a_core = (a.major, a.minor, a.patch)
    b_core = (b.major, b.minor, b.patch)
    if a_core != b_core:
        return -1 if a_core < b_core else 1
    if not a.prerelease and not b.prerelease:
        return 0
    if not a.prerelease:
        return 1
    if not b.prerelease:
        return -1
    for a_id, b_id in zip(a.prerelease, b.prerelease):
        if a_id == b_id:
            continue
        a_numeric = a_id.isdigit()
        b_numeric = b_id.isdigit()
        if a_numeric and b_numeric:
            return -1 if int(a_id) < int(b_id) else 1
        if a_numeric != b_numeric:
            return -1 if a_numeric else 1
        return -1 if a_id < b_id else 1
    if len(a.prerelease) == len(b.prerelease):
        return 0
    return -1 if len(a.prerelease) < len(b.prerelease) else 1


def _required_text(
    manifest: dict[str, Any], key: str, *, maximum: int = 500
) -> str:
    value = manifest.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise UpdateCheckError(f"manifest field {key!r} must be non-empty text")
    normalized = value.strip()
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise UpdateCheckError(f"manifest field {key!r} must be single-line text")
    return normalized


def validate_manifest(payload: Any) -> dict[str, Any]:
    """Validate and normalize the fixed repository's stable update manifest."""

    if not isinstance(payload, dict):
        raise UpdateCheckError("update manifest must be a JSON object")
    if payload.get("schema_version") != 1:
        raise UpdateCheckError("unsupported update manifest schema")
    if payload.get("skill") != SKILL_NAME:
        raise UpdateCheckError("update manifest names a different skill")
    if payload.get("repository") != REPOSITORY:
        raise UpdateCheckError("update manifest names a different repository")
    if payload.get("channel") != "stable":
        raise UpdateCheckError("only the stable update channel is accepted")

    version = _required_text(payload, "version", maximum=64)
    parsed_version = parse_version(version)
    if parsed_version.prerelease:
        raise UpdateCheckError("the stable channel cannot publish a prerelease version")
    tag = _required_text(payload, "tag", maximum=65)
    if tag != f"v{version}":
        raise UpdateCheckError("manifest tag must exactly match v<version>")

    minimum_protocol = payload.get("minimum_updater_protocol")
    if not isinstance(minimum_protocol, int) or isinstance(minimum_protocol, bool):
        raise UpdateCheckError("minimum_updater_protocol must be an integer")
    if minimum_protocol < 1:
        raise UpdateCheckError("minimum_updater_protocol must be positive")

    published_at = _required_text(payload, "published_at", maximum=32)
    try:
        parsed_date = date.fromisoformat(published_at)
    except ValueError as exc:
        raise UpdateCheckError("published_at must be a valid YYYY-MM-DD date") from exc
    if parsed_date.isoformat() != published_at:
        raise UpdateCheckError("published_at must use YYYY-MM-DD")
    summary = _required_text(payload, "summary", maximum=500)
    changes = payload.get("changes")
    if not isinstance(changes, list) or len(changes) > 20:
        raise UpdateCheckError("changes must be a list with at most 20 entries")
    normalized_changes: list[str] = []
    for change in changes:
        normalized_changes.append(
            _required_text({"change": change}, "change", maximum=500)
        )

    return {
        "schema_version": 1,
        "skill": SKILL_NAME,
        "repository": REPOSITORY,
        "channel": "stable",
        "version": version,
        "tag": tag,
        "minimum_updater_protocol": minimum_protocol,
        "published_at": published_at,
        "summary": summary,
        "changes": normalized_changes,
    }


def read_local_version(skill_root: Path) -> str:
    """Read and validate VERSION from an installed skill root."""

    version_path = skill_root / "VERSION"
    try:
        value = version_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise UpdateCheckError(f"cannot read local VERSION: {exc}") from exc
    if len(value) > 64:
        raise UpdateCheckError("local VERSION is unexpectedly long")
    parse_version(value)
    return value


def _fetch_json(
    url: str,
    *,
    expected_host: str,
    expected_path: str,
    maximum: int,
    timeout: float,
) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{SKILL_NAME}-updater/{UPDATER_PROTOCOL_VERSION}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            final_url = response.geturl()
            parsed = urllib.parse.urlparse(final_url)
            if (
                parsed.scheme != "https"
                or parsed.hostname != expected_host
                or parsed.path != expected_path
            ):
                raise UpdateCheckError("update request redirected outside the trusted path")
            length = response.headers.get("Content-Length")
            if length is not None and int(length) > maximum:
                raise UpdateCheckError("update metadata is unexpectedly large")
            raw = response.read(maximum + 1)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise UpdateCheckError(f"cannot retrieve update metadata: {exc}") from exc
    if len(raw) > maximum:
        raise UpdateCheckError("update metadata is unexpectedly large")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateCheckError(f"update metadata is not valid UTF-8 JSON: {exc}") from exc


def _validated_sha(value: Any) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise UpdateCheckError("release tag did not resolve to a valid commit SHA")
    return value


def _remaining_timeout(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise UpdateCheckError("the overall update-check deadline expired")
    return remaining


def resolve_tag_commit(
    tag: str, timeout: float = 5.0, *, deadline: float | None = None
) -> str:
    """Resolve a lightweight or annotated release tag to one exact commit."""

    if deadline is None:
        deadline = time.monotonic() + timeout
    version = tag.removeprefix("v")
    parse_version(version)
    if tag != f"v{version}":
        raise UpdateCheckError("release tag must exactly match v<version>")
    encoded_tag = urllib.parse.quote(tag, safe="")
    ref_path = f"/repos/{REPOSITORY}/git/ref/tags/{encoded_tag}"
    payload = _fetch_json(
        f"https://api.github.com{ref_path}",
        expected_host="api.github.com",
        expected_path=ref_path,
        maximum=MAX_RELEASE_BYTES,
        timeout=_remaining_timeout(deadline),
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("object"), dict):
        raise UpdateCheckError("release tag response is invalid")
    object_payload = payload["object"]
    object_type = object_payload.get("type")
    object_sha = _validated_sha(object_payload.get("sha"))
    for _ in range(3):
        if object_type == "commit":
            return object_sha
        if object_type != "tag":
            raise UpdateCheckError("release tag does not point to a commit")
        tag_path = f"/repos/{REPOSITORY}/git/tags/{object_sha}"
        payload = _fetch_json(
            f"https://api.github.com{tag_path}",
            expected_host="api.github.com",
            expected_path=tag_path,
            maximum=MAX_RELEASE_BYTES,
            timeout=_remaining_timeout(deadline),
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("object"), dict):
            raise UpdateCheckError("annotated release tag response is invalid")
        object_payload = payload["object"]
        object_type = object_payload.get("type")
        object_sha = _validated_sha(object_payload.get("sha"))
    raise UpdateCheckError("release tag indirection is unexpectedly deep")


def validate_release_info(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise UpdateCheckError("release information must be an object")
    manifest = validate_manifest(payload.get("manifest"))
    commit = _validated_sha(payload.get("commit"))
    expected_url = release_url(manifest["tag"])
    if payload.get("release_url") != expected_url:
        raise UpdateCheckError("release URL does not match the fixed repository and tag")
    return {"manifest": manifest, "commit": commit, "release_url": expected_url}


def fetch_release_info(timeout: float = 5.0) -> dict[str, Any]:
    """Resolve the latest published release and its manifest to an exact commit."""

    deadline = time.monotonic() + timeout
    release = _fetch_json(
        LATEST_RELEASE_URL,
        expected_host="api.github.com",
        expected_path=_RELEASE_PATH,
        maximum=MAX_RELEASE_BYTES,
        timeout=_remaining_timeout(deadline),
    )
    if not isinstance(release, dict):
        raise UpdateCheckError("latest release response is invalid")
    if release.get("draft") is not False or release.get("prerelease") is not False:
        raise UpdateCheckError("latest release is not a published stable release")
    tag = release.get("tag_name")
    if not isinstance(tag, str):
        raise UpdateCheckError("latest release has no semantic-version tag")
    commit = resolve_tag_commit(tag, timeout, deadline=deadline)
    manifest_path = f"/{REPOSITORY}/{commit}/skill-manifest.json"
    manifest = validate_manifest(
        _fetch_json(
            f"https://raw.githubusercontent.com{manifest_path}",
            expected_host="raw.githubusercontent.com",
            expected_path=manifest_path,
            maximum=MAX_MANIFEST_BYTES,
            timeout=_remaining_timeout(deadline),
        )
    )
    if manifest["tag"] != tag:
        raise UpdateCheckError("release tag differs from the release manifest")
    published_at = release.get("published_at")
    if not isinstance(published_at, str) or published_at[:10] != manifest["published_at"]:
        raise UpdateCheckError("release publication date differs from the manifest")
    return validate_release_info(
        {
            "manifest": manifest,
            "commit": commit,
            "release_url": release_url(tag),
        }
    )


def fetch_manifest(timeout: float = 5.0) -> dict[str, Any]:
    """Compatibility name for callers; returns release plus manifest information."""

    return fetch_release_info(timeout)


def release_url(tag: str) -> str:
    return f"https://github.com/{REPOSITORY}/releases/tag/{tag}"


def check_for_update(
    skill_root: Path,
    *,
    manifest_loader: Callable[[], dict[str, Any]] = fetch_release_info,
) -> dict[str, Any]:
    """Return a non-mutating status payload suitable for agents or humans."""

    installed = read_local_version(skill_root)
    if skill_root.is_symlink():
        installation_mode = "symlink"
    elif (skill_root / ".git").exists():
        installation_mode = "git_checkout"
    elif not (
        os.access(skill_root, os.R_OK | os.W_OK | os.X_OK)
        and os.access(skill_root.parent, os.W_OK | os.X_OK)
    ):
        installation_mode = "read_only"
    else:
        installation_mode = "managed_copy"
    try:
        release = validate_release_info(manifest_loader())
        manifest = release["manifest"]
    except UpdateCheckError as exc:
        return {
            "status": "unavailable",
            "installed_version": installed,
            "message": str(exc),
            "continue_with_installed": True,
        }

    available = manifest["version"]
    comparison = compare_versions(installed, available)
    common = {
        "installed_version": installed,
        "available_version": available,
        "tag": manifest["tag"],
        "published_at": manifest["published_at"],
        "summary": manifest["summary"],
        "changes": manifest["changes"],
        "release_url": release_url(manifest["tag"]),
        "commit": release["commit"],
        "installation_mode": installation_mode,
    }
    if comparison == 0:
        return {"status": "current", **common}
    if comparison > 0:
        return {
            "status": "local_ahead",
            **common,
            "message": "The installed version is newer than the stable channel.",
        }
    if installation_mode == "git_checkout":
        return {
            "status": "manual_update_required",
            **common,
            "can_auto_update": False,
            "message": (
                "This installation is a Git checkout and will not be replaced "
                "automatically. Update it with a reviewed Git workflow or reinstall "
                "the tagged release as a managed copy."
            ),
        }
    if installation_mode == "symlink":
        return {
            "status": "manual_update_required",
            **common,
            "can_auto_update": False,
            "message": (
                "This installation is reached through a symbolic link and will not be "
                "replaced automatically. Update its real target through the host's "
                "normal reviewed workflow."
            ),
        }
    if installation_mode == "read_only":
        return {
            "status": "manual_update_required",
            **common,
            "can_auto_update": False,
            "message": (
                "This installation or its parent directory is not writable. Use the "
                "host's normal skill import or reinstall flow for the tagged release."
            ),
        }
    if manifest["minimum_updater_protocol"] > UPDATER_PROTOCOL_VERSION:
        return {
            "status": "manual_update_required",
            **common,
            "can_auto_update": False,
            "message": "The stable release requires a newer updater protocol.",
        }
    return {
        "status": "update_available",
        **common,
        "can_auto_update": True,
    }


def _print_human(result: dict[str, Any]) -> None:
    status = result["status"]
    installed = result["installed_version"]
    if status == "current":
        print(f"Audit Scientific Papers {installed} is current.")
    elif status == "local_ahead":
        print(result["message"])
    elif status == "unavailable":
        print(f"Update status unavailable; continue with {installed}: {result['message']}")
    else:
        available = result["available_version"]
        print(f"Audit Scientific Papers {available} is available (installed: {installed}).")
        print(result["summary"])
        for change in result["changes"]:
            print(f"- {change}")
        print(f"Published: {result['published_at']}")
        print(f"Exact release commit: {result['commit']}")
        print(result["release_url"])
        if status == "manual_update_required":
            print(result["message"])


def installation_health(skill_root: Path) -> dict[str, Any]:
    """Conservatively decide whether a failed checker may continue the audit."""

    try:
        expanded = skill_root.expanduser()
        if expanded.is_symlink():
            raise OSError("skill root is a symbolic link")
        root = expanded.resolve(strict=True)
        version = read_local_version(root)
        required = (
            root / "SKILL.md",
            root / "references" / "update-protocol.md",
            root / "scripts" / "check_for_update.py",
            root / "scripts" / "update_skill.py",
        )
        intact = root.is_dir() and root.name == SKILL_NAME
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
    except (OSError, UnicodeError, UpdateCheckError):
        return {"installation_intact": False, "continue_with_installed": False}
    return {
        "installation_intact": intact,
        "continue_with_installed": intact,
        "installed_version": version,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--timeout", type=float, default=5.0, help="network timeout in seconds"
    )
    parser.add_argument(
        "--skill-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.timeout > 60:
        parser.error("--timeout must be greater than 0 and at most 60")
    try:
        result = check_for_update(
            args.skill_root.expanduser(),
            manifest_loader=lambda: fetch_manifest(args.timeout),
        )
    except UpdateCheckError as exc:
        result = {
            "status": "error",
            "message": str(exc),
            **installation_health(args.skill_root),
        }
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Update check failed: {exc}")
        return 2
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        _print_human(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
