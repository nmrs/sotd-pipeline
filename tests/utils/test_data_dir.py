"""Tests for sotd.utils.data_dir.get_data_dir path resolution.

Covers the consolidation contract every consumer of the run's data dir
relies on: env var / CLI precedence, repo-root anchoring of relative
values, and ``~`` expansion — all independent of the process CWD.
"""

from pathlib import Path

import pytest

from sotd.utils.data_dir import _repo_root, get_data_dir


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("SOTD_DATA_DIR", raising=False)


def test_env_var_used(clean_env, monkeypatch):
    monkeypatch.setenv("SOTD_DATA_DIR", "/abs/data")
    assert get_data_dir(None) == Path("/abs/data")


def test_cli_arg_wins_over_env(clean_env, monkeypatch):
    monkeypatch.setenv("SOTD_DATA_DIR", "/env/data")
    assert get_data_dir("/cli/data") == Path("/cli/data")


def test_default_used_when_env_unset(clean_env):
    repo = _repo_root()
    assert repo is not None
    assert get_data_dir(None) == repo / "data"


def test_tilde_env_var_expanded(clean_env, monkeypatch):
    """A ~-prefixed env value (compose env files deliver it verbatim) must
    expand to the home directory, not land inside <repo>/~/... ."""
    monkeypatch.setenv("SOTD_DATA_DIR", "~/sotd-data")
    resolved = get_data_dir(None)
    assert resolved.is_absolute()
    assert resolved == Path("~/sotd-data").expanduser()


def test_tilde_cli_arg_expanded(clean_env):
    resolved = get_data_dir("~/sotd-data")
    assert resolved.is_absolute()
    assert resolved == Path("~/sotd-data").expanduser()


def test_relative_default_anchored_at_repo_root_from_foreign_cwd(clean_env, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    repo = _repo_root()
    assert repo is not None
    assert get_data_dir(None) == repo / "data"


def test_relative_env_var_anchored_at_repo_root_from_foreign_cwd(clean_env, monkeypatch, tmp_path):
    monkeypatch.setenv("SOTD_DATA_DIR", "data2")
    monkeypatch.chdir(tmp_path)
    repo = _repo_root()
    assert repo is not None
    assert get_data_dir(None) == repo / "data2"


def test_tilde_env_var_expanded_before_anchoring(clean_env, monkeypatch, tmp_path):
    """A ~-value is expanded before the relative-anchoring step, so it never
    gets prefixed with the repo root."""
    monkeypatch.setenv("SOTD_DATA_DIR", "~/sotd-data")
    monkeypatch.chdir(tmp_path)
    resolved = get_data_dir(None)
    assert _repo_root() not in resolved.parents


def test_default_cli_value_still_checks_env(clean_env, monkeypatch):
    """argparse passes the literal default "data" when --data-dir is
    omitted; that must not suppress the env var."""
    monkeypatch.setenv("SOTD_DATA_DIR", "/env/data")
    assert get_data_dir(Path("data")) == Path("/env/data")
