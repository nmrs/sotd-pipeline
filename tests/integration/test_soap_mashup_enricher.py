"""Production-catalog tests: the SoapMashupEnricher default soaps.yaml
resolves from the run's data dir (#23 instance).

This test asserts against a live production catalog entry (Mama Bear's
Soaps / Sample Mashup is countable: false in data/soaps.yaml), so it lives
here under ``tests/integration/`` with the ``production`` marker (run with
``make test-production``) rather than in the default unit suite: a routine
data edit must not break ``make test`` with failures unrelated to any code
change. The path-resolution tests using synthetic fixture data stay in
``tests/enrich/test_soap_mashup_enricher.py``.

Note: CI's default ``pytest tests/`` invocation still runs this file (it
only deselects ``-m "not perf"``), so the move is the repo convention for
catalog-asserting tests, not an exclusion from the default suite.
"""

from pathlib import Path

import pytest

from sotd.enrich.soap_mashup_enricher import SoapMashupEnricher

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.production
def test_default_anchored_at_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """No env var + foreign CWD still finds the repo's data/soaps.yaml."""
    monkeypatch.delenv("SOTD_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)  # no data/ here

    enricher = SoapMashupEnricher()
    assert enricher.soaps_path == REPO_ROOT / "data" / "soaps.yaml"
    # Real catalog lookup: Mama Bear's Soaps / Sample Mashup is
    # countable: false in data/soaps.yaml.
    result = enricher.enrich(
        {
            "original": "Mama Bear Tri-Mix",
            "normalized": "mama bear tri-mix",
            "matched": {"brand": "Mama Bear's Soaps", "scent": "Sample Mashup"},
        },
        "",
    )
    assert result == {"is_mashup": True}
