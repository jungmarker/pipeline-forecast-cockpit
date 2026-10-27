"""Quarterly bookings forecast with an honest back-test.

For each past quarter we rebuild the pipeline exactly as it looked on day one (stage history up to that
date only), forecast the quarter, and compare with what actually closed. Methods:

- crm_weighted:  amount × default stage probability, summed over all open deals (what most CRM dashboards show)
- crm_plus_runrate: the same, plus the average bookings from deals created and won inside a quarter
- conversion_model: per-deal probability of closing won *this quarter*, learned only from earlier quarters
  (by type, segment, stage and deal age), plus the in-quarter run-rate; P10/P90 from simulation
"""
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

CRM_STAGE_PROB = {"Discovery": 0.10, "Demo": 0.20, "Proposal": 0.50, "Negotiation": 0.75}
TYPES = ("New Business", "Renewal", "Expansion")
SHRINK = 10  # pseudo-deals pulling a thin segment's rate toward its stage average


def quarter_starts(first: date, last: date) -> list[date]:
    return [d.date() for d in pd.date_range(first, last, freq="QS")]


def quarter_end(d: date) -> date:
    return (pd.Timestamp(d) + pd.offsets.QuarterBegin(startingMonth=1)).date()


def snapshot(con, d: date, truth: pd.DataFrame | None = None) -> pd.DataFrame:
    """Open deals as of the morning of d, with the stage they were in then and whether they were won by quarter end."""
    q_end = quarter_end(d)
    snap = con.execute("""
        with at_date as (
            select opportunity_id, arg_max(stage, entered_at) as stage_at
            from raw.opportunity_stage_history where entered_at < ? group by 1
        )
        select o.opportunity_id, o.type, o.segment, o.amount, o.created_date, o.is_won, o.close_date, a.stage_at,
               datediff('day', o.created_date, ?::date) as age_days
        from opps o join at_date a using (opportunity_id)
        where o.created_date < ? and a.stage_at not in ('Closed Won', 'Closed Lost')
    """, [d, d, d]).df()
    snap["won_this_q"] = snap.is_won.fillna(False).astype(bool) & (pd.to_datetime(snap.close_date).dt.date < q_end)
    if truth is not None:  # live quarter: outcome comes from the hidden answer key
        t = truth.set_index("opportunity_id")
        open_now = snap.opportunity_id.isin(t.index)
        tc = pd.to_datetime(snap.opportunity_id.map(t.true_close_date)).dt.date
        snap.loc[open_now, "won_this_q"] = (snap.opportunity_id.map(t.will_win).astype(bool) & (tc < q_end))[open_now]
    snap["age_bucket"] = pd.cut(snap.age_days, [-1, 30, 90, 10_000], labels=["<30d", "30-90d", ">90d"]).astype(str)
    snap["quarter"] = d
    return snap


def created_in_quarter(con, d: date) -> pd.Series:
    """Bookings from deals both created and won inside the quarter, by type."""
    q_end = quarter_end(d)
    s = con.execute("""select type, sum(amount) as acv from opps
                       where is_won and created_date >= ? and close_date < ? group by 1""", [d, q_end]).df()
    return s.set_index("type").acv.reindex(TYPES, fill_value=0.0)


def _rates(history: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    parent = history.groupby(["type", "stage_at"]).won_this_q.agg(["sum", "count"])
    parent["p"] = (parent["sum"] + 1) / (parent["count"] + 2)
    child = history.groupby(["type", "segment", "stage_at", "age_bucket"]).won_this_q.agg(["sum", "count"])
    return parent, child


def deal_probability(snap: pd.DataFrame, history: pd.DataFrame) -> np.ndarray:
    parent, child = _rates(history)
    p_parent = snap.set_index(["type", "stage_at"]).index.map(parent.p).to_numpy(dtype=float)
    p_parent = np.where(np.isnan(p_parent), snap.stage_at.map(CRM_STAGE_PROB).to_numpy(float), p_parent)
    idx = snap.set_index(["type", "segment", "stage_at", "age_bucket"]).index
    wins = idx.map(child["sum"]).to_numpy(dtype=float)
    n = idx.map(child["count"]).to_numpy(dtype=float)
    wins, n = np.nan_to_num(wins), np.nan_to_num(n)
    return (wins + SHRINK * p_parent) / (n + SHRINK)


def impute_amount(snap: pd.DataFrame, history_won: pd.DataFrame) -> pd.Series:
    med = history_won.groupby(["type", "segment"]).amount.median()
    fill = snap.set_index(["type", "segment"]).index.map(med).to_numpy(dtype=float)
    return snap.amount.fillna(pd.Series(fill, index=snap.index)).fillna(0)


@dataclass
class QuarterForecast:
    quarter: date
    by_type: pd.DataFrame  # index type; columns per method + actual


def forecast_quarter(con, d: date, history: pd.DataFrame, runrate_hist: pd.DataFrame, won_hist: pd.DataFrame,
                     truth=None, sims: int = 4000, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    snap = snapshot(con, d, truth)
    snap["crm_p"] = snap.stage_at.map(CRM_STAGE_PROB)
    snap["amount_est"] = impute_amount(snap, won_hist)
    snap["model_p"] = deal_probability(snap, history) if len(history) else snap.crm_p
    runrate = runrate_hist.tail(4).mean() if len(runrate_hist) else pd.Series(0.0, index=TYPES)

    rng = np.random.default_rng(seed)
    rows = []
    for t in TYPES:
        s = snap[snap.type == t]
        crm = float((s.amount.fillna(0) * s.crm_p).sum())
        model_open = float((s.amount_est * s.model_p).sum())
        # Simulation: each deal wins or not; in-quarter bookings drawn from the last 4 quarters
        wins = rng.random((sims, len(s))) < s.model_p.to_numpy()
        open_sims = wins.astype(float) @ s.amount_est.to_numpy()
        rr = runrate_hist[t].tail(4).to_numpy() if len(runrate_hist) else np.zeros(1)
        sim = open_sims + rng.choice(rr, size=sims)
        rows.append(dict(type=t, open_deals=len(s), open_acv=float(s.amount.fillna(0).sum()),
                         crm_weighted=crm, crm_plus_runrate=crm + runrate[t],
                         conversion_model=model_open + runrate[t], p10=float(np.percentile(sim, 10)),
                         p90=float(np.percentile(sim, 90)),
                         actual_from_open=float(s.amount.fillna(0)[s.won_this_q].sum())))
    return pd.DataFrame(rows).set_index("type"), snap


def backtest(con, first: date, last: date, live: date | None = None, truth=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Walk forward one quarter at a time; each forecast only sees quarters that already ended."""
    results, history, runrate = [], [], []
    won_all = con.execute("select type, segment, amount, close_date from opps where is_won").df()
    quarters = quarter_starts(first, last)
    for i, d in enumerate(quarters + ([live] if live else [])):
        hist = pd.concat(history) if history else pd.DataFrame(columns=["type", "segment", "stage_at", "age_bucket", "won_this_q"])
        rr = pd.DataFrame(runrate) if runrate else pd.DataFrame(columns=TYPES)
        won_hist = won_all[pd.to_datetime(won_all.close_date).dt.date < d]
        is_live = live is not None and d == live
        fc, snap = forecast_quarter(con, d, hist, rr, won_hist, truth if is_live else None)
        inq = created_in_quarter(con, d)
        fc["actual_in_quarter_created"] = np.nan if is_live else inq.reindex(fc.index).values
        fc["actual"] = fc.actual_from_open + (0 if is_live else fc.actual_in_quarter_created)
        fc["quarter"], fc["live"] = d, is_live
        results.append(fc.reset_index())
        history.append(snap)
        runrate.append(inq)
    return pd.concat(results, ignore_index=True), pd.concat(history, ignore_index=True)


def accuracy(bt: pd.DataFrame, warmup: int = 4) -> pd.DataFrame:
    """MAPE and bias per method on completed quarters, after a warm-up period so rates have history."""
    done = bt[~bt.live]
    done = done[done.quarter >= sorted(done.quarter.unique())[warmup]]
    total = done.groupby("quarter")[["crm_weighted", "crm_plus_runrate", "conversion_model", "p10", "p90", "actual"]].sum()
    rows = []
    for m in ("crm_weighted", "crm_plus_runrate", "conversion_model"):
        err = (total[m] - total.actual) / total.actual
        rows.append(dict(method=m, mape=float(err.abs().mean()), bias=float(err.mean()),
                         worst_quarter_error=float(err.abs().max())))
    out = pd.DataFrame(rows).set_index("method")
    out.attrs["interval_coverage"] = float(((total.actual >= total.p10) & (total.actual <= total.p90)).mean())
    out.attrs["quarters"] = len(total)
    return out
