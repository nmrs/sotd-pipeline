"""
Data directory path resolution utility.

Provides a unified way to determine the data directory path with precedence:
1. CLI argument (--data-dir)
2. SOTD_DATA_DIR environment variable
3. Default: ./data

A relative data dir is anchored at the repo root, so every consumer resolves
the same env var / CLI value to the same tree regardless of the process
working directory. (Previously ``get_data_dir()`` returned relative paths
CWD-anchored while the per-phase default-path helpers anchored the same
value at the repo root, so two layers resolved one env var to different
trees.)
"""

import os
from pathlib import Path
from typing import Optional


def _repo_root() -> Optional[Path]:
    """Repo root, found by walking up from this file.

    The root is the first ancestor containing both a ``pyproject.toml``
    and the ``sotd`` package directory. Returns ``None`` when the package
    is installed (e.g. under site-packages) rather than checked out: there
    is no repo root to anchor at, so the ``__file__``-based parent hop the
    old code used -- which resolved to site-packages and produced a
    legitimate-looking but wrong absolute path -- is never returned.
    Callers fall back to the unanchored (CWD-relative) path in that case,
    and an absolute data dir via ``--data-dir`` / ``SOTD_DATA_DIR`` is
    required to run from elsewhere.
    """
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file() and (parent / "sotd").is_dir():
            return parent
    return None


def get_data_dir(cli_arg: Optional[Path | str] = None) -> Path:
    """
    Get data directory path with precedence: CLI arg > env var > default.

    A relative result is anchored at the repo root (see ``_repo_root``),
    so the returned path never depends on the process working directory.
    A ``~``-prefixed value (env var or CLI arg) is expanded to the home
    directory before anchoring — compose env files deliver
    ``SOTD_DATA_DIR='~/sotd-data'`` verbatim, and every consumer must agree
    on one tree for it. Absolute values are returned unchanged. When the
    package is installed rather than checked out (no repo root found), a
    relative result is returned unanchored, as before.

    Args:
        cli_arg: Optional Path or str from CLI argument (--data-dir).
                 If None or equals default "data", checks SOTD_DATA_DIR env var first.

    Returns:
        Path: Resolved data directory path

    Examples:
        >>> get_data_dir(Path("/custom/path")) == Path("/custom/path")
        True

        >>> os.environ['SOTD_DATA_DIR'] = '/data'
        >>> get_data_dir(None) == Path('/data')
        True
        >>> get_data_dir(Path("data")) == Path('/data')
        True

        >>> os.environ['SOTD_DATA_DIR'] = '~/sotd-data'
        >>> get_data_dir(None) == Path('~/sotd-data').expanduser()
        True

        >>> del os.environ['SOTD_DATA_DIR']
        >>> get_data_dir(None) == _repo_root() / "data"  # anchored at the repo root
        True
    """
    # Convert to Path for comparison
    cli_path = Path(cli_arg) if cli_arg is not None else None
    default_path = Path("data")

    # If CLI arg is None or equals the default, check env var first
    # This allows env var to work even when argparse uses default value
    if cli_path is None or cli_path == default_path:
        sotd_data_dir = os.environ.get("SOTD_DATA_DIR")
        if sotd_data_dir:
            data_dir = Path(sotd_data_dir)
        else:
            # If no env var, use the default (or the provided default if explicitly given)
            data_dir = default_path if cli_path is None else cli_path
    else:
        # CLI argument takes highest precedence (non-default value)
        data_dir = cli_path

    # Expand a leading ~ before anchoring: Path("~/sotd-data") is not
    # absolute, so a ~-value anchored first would land inside <repo>/~/...
    # (compose env files deliver the env var verbatim).
    data_dir = data_dir.expanduser()

    # Anchor relative data dirs at the repo root so all consumers agree
    # on one tree for the same value, whatever the working directory.
    if not data_dir.is_absolute():
        repo_root = _repo_root()
        if repo_root is not None:
            data_dir = repo_root / data_dir
    return data_dir


def get_default_correct_matches_path() -> Path:
    """Default correct_matches directory: ``<data dir>/correct_matches``.

    The data dir is the run's data dir (``get_data_dir()``: ``--data-dir`` >
    ``SOTD_DATA_DIR`` env var > ``"data"``), with relative values anchored
    at the repo root inside ``get_data_dir()`` -- so this path never depends
    on the process working directory. Previously the matchers defaulted to
    a bare CWD-relative ``Path("data/correct_matches")``, so constructing a
    matcher from any directory but the repo root silently loaded no correct
    matches and the matcher fell back to regex-only matching.
    """
    return get_data_dir() / "correct_matches"
