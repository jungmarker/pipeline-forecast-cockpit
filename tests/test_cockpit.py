from datetime import date

import pandas as pd
import pytest

from cockpit import forecast as F
from cockpit.cli import build
from cockpit.warehouse import connect

gen = pytest.importorskip("ledgerly.generate")


@pytest.fixture(scope="session")
def db(tmp_path_factory):
    out = tmp_path_factory.mktemp("ledgerly")
    gen.write(gen.build(seed=7), out)
    return str(out / "ledgerly.duckdb")


@pytest.fixture(scope="session")
def con(db):
    return connect(db)


def test_quarter_helpers():
    assert F.quarter_end(date(2025, 2, 14)) == date(2025, 4, 1)
    assert F.quarter_end(date(2025, 12, 31)) == date(2026, 1, 1)
    assert F.quarter_starts(date(2025, 1, 1), date(2025, 12, 31))[-1] == date(2025, 10, 1)


def test_snapshot_uses_only_the_past(con):
    d = date(2025, 4, 1)
    snap = F.snapshot(con, d)
    assert (pd.to_datetime(snap.created_date).dt.date < d).all()
    assert snap.stage_at.isin(F.CRM_STAGE_PROB).all()  # nothing already closed on that morning
    # Every deal in the snapshot closed on or after d (or is still open)
    closed = snap.close_date.notna() & snap.is_won.notna()
    assert (pd.to_datetime(snap.close_date[closed]).dt.date >= d).all()
    # Stage on that morning matches the last history row before d
    h = con.execute("select opportunity_id, stage, entered_at from raw.opportunity_stage_history").df()
    h = h[h.entered_at < pd.Timestamp(d)].sort_values("entered_at").groupby("opportunity_id").stage.last()
    assert (snap.set_index("opportunity_id").stage_at == h.reindex(snap.opportunity_id).values).all()


def test_won_this_quarter_means_closed_before_quarter_end(con):
    d = date(2025, 4, 1)
    snap = F.snapshot(con, d)
    won = snap[snap.won_this_q]
    assert (pd.to_datetime(won.close_date).dt.date < F.quarter_end(d)).all() and won.is_won.all()


def test_probabilities_bounded(con):
    hist = pd.concat([F.snapshot(con, q) for q in F.quarter_starts(date(2024, 1, 1), date(2024, 12, 31))])
    p = F.deal_probability(F.snapshot(con, date(2025, 4, 1)), hist)
    assert ((p > 0) & (p < 1)).all()


def test_backtest_beats_crm_weighting_on_unseen_company(db, tmp_path):
    """Seed 7 was never used to design the model; the conversion model should still be clearly better."""
    data = build(db, tmp_path)
    acc = {r["method"]: r for r in data["accuracy"]}
    assert acc["conversion_model"]["mape"] < 0.20
    assert acc["conversion_model"]["mape"] < acc["crm_weighted"]["mape"] / 2
    assert abs(acc["conversion_model"]["bias"]) < 0.10
    assert (tmp_path / "index.html").stat().st_size > 10_000
