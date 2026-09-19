"""Smoke tests: the web app runs end to end on the sample submission."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = Path(__file__).resolve().parents[1] / "app.py"


def run_app() -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception
    return at


def load_sample(at: AppTest) -> AppTest:
    next(c for c in at.checkbox if "sample" in c.label).check().run()
    assert not at.exception
    return at


def open_review(at: AppTest) -> AppTest:
    next(b for b in at.button if "Review changes" in b.label).click().run()
    assert not at.exception
    return at


def dl_text(at: AppTest) -> str:
    return next(m.value for m in at.markdown if 'class="dl-text"' in m.value)


def test_starts_empty_with_placeholder_stats():
    at = run_app()
    assert "Nothing to download yet" in dl_text(at)
    assert any("??" in m.value for m in at.markdown)


def test_sample_loads_with_review_closed():
    at = load_sample(run_app())
    assert "0 changes approved" in dl_text(at)
    assert not at.selectbox  # review section stays closed until asked for


def test_choosing_a_station_approves_one_change():
    at = open_review(load_sample(run_app()))
    box = next(b for b in at.selectbox if "London Victoria" in b.options)
    box.select("London Victoria").run()
    assert not at.exception
    assert "1 change approved" in dl_text(at)


def test_approve_all_approves_every_proposal_and_survives_closing():
    at = open_review(load_sample(run_app()))
    next(b for b in at.button if b.label == "Approve all").click().run()
    assert "23 changes approved" in dl_text(at)
    open_review(at)  # close the review section again
    assert "23 changes approved" in dl_text(at)