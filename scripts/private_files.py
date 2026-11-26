"""Owner-only, symlink-safe writes for candidate private artifacts.

Public checkout safety is deliberately conservative: a destination inside any
Git checkout must be ignored by Git. External directories need no repository.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class PrivateOutputError(ValueError):
    """An output path or write cannot be kept private."""


def _git_root(path: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            check=True, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(result.stdout.strip())


def private_destination(path: Path | str) -> Path:
    """Resolve a destination that is symlink-safe and private by construction."""
    destination = Path(path).expanduser()
    resolved = destination.resolve(strict=False)
    temp_root = Path(tempfile.gettempdir()).expanduser()
    canonical_temp = temp_root.resolve()
    for part in (destination,) + tuple(destination.parents):
        if not part.is_symlink():
            continue
        # /var -> /private/var (and similar temp roots) is a platform alias.
        # A symlink supplied inside that root must still be rejected.
        platform_alias = (part == temp_root or part in temp_root.parents
                          or part == canonical_temp or part in canonical_temp.parents)
        if not platform_alias:
            raise PrivateOutputError("Private output paths must not cross a symlink.")
    repo = _git_root(resolved.parent if resolved.parent.exists() else Path.cwd())
    if repo is not None:
        try:
            relative = resolved.relative_to(repo.resolve())
        except ValueError:
            relative = None
        if relative is not None:
            try:
                tracked = subprocess.run(
                    ["git", "-C", str(repo), "ls-files", "--error-unmatch", "--", str(relative)],
                    capture_output=True, timeout=5).returncode == 0
                ignored = subprocess.run(
                    ["git", "-C", str(repo), "check-ignore", "--quiet", "--", str(relative)],
                    capture_output=True, timeout=5).returncode == 0
            except (OSError, subprocess.SubprocessError) as error:
                raise PrivateOutputError("Cannot verify private Git storage.") from error
            if tracked or not ignored:
                raise PrivateOutputError(
                    "Private output cannot be written into a public checkout unless Git ignores it.")
    return destination


def write_private_text(path: Path | str, text: str) -> Path:
    """Atomically write text with 0600 permissions, never a world-readable window."""
    destination = private_destination(path)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, staging = tempfile.mkstemp(prefix=".private-", dir=destination.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging, destination)
    finally:
        if os.path.exists(staging):
            os.unlink(staging)
    os.chmod(destination, 0o600)
    return destination
