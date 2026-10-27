"""cockpit build --db data/ledgerly.duckdb --out report/"""
import argparse
import json
from pathlib import Path

from . import forecast as F
from .report import render
from .warehouse import connect, has_truth, sql


def build(db: str, out: Path) -> dict:
    con = connect(db)
    as_of = con.execute("select max(entered_at)::date from raw.opportunity_stage_history").fetchone()[0]
    live = F.quarter_end(as_of)  # first day of the next quarter: the one being forecast now
    first_hist = con.execute("select min(created_date) from opps").fetchone()[0]
    first = F.quarter_starts(first_hist, live)[1]
    truth = con.execute("select * from src.truth.open_opportunity_outcomes").df() if has_truth(con) else None
    bt, _ = F.backtest(con, first, F.quarter_starts(first, live)[-2], live=live, truth=truth)
    acc = F.accuracy(bt)
    q = lambda name, **p: con.execute(sql(name, **p)).df()
    data = {
        "as_of": str(as_of), "live_quarter": str(live), "has_truth": truth is not None,
        "backtest": bt.assign(quarter=bt.quarter.astype(str)).round(0).to_dict("records"),
        "accuracy": acc.reset_index().to_dict("records"),
        "interval_coverage": acc.attrs["interval_coverage"], "backtest_quarters": acc.attrs["quarters"],
        "funnel": q("funnel").to_dict("records"),
        "velocity": q("velocity").to_dict("records"),
        "win_rates": q("win_rates").to_dict("records"),
        "hygiene": q("hygiene", as_of=as_of).head(15).to_dict("records"),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render(data))
    (out / "backtest.csv").write_text(bt.to_csv(index=False))
    (out / "accuracy.json").write_text(json.dumps(data["accuracy"], indent=1))
    return data


def main(argv=None):
    p = argparse.ArgumentParser(prog="cockpit")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="back-test the forecast and write the dashboard")
    b.add_argument("--db", required=True)
    b.add_argument("--out", default=Path("report"), type=Path)
    a = p.parse_args(argv)
    d = build(a.db, a.out)
    for r in d["accuracy"]:
        print(f"{r['method']:18s} MAPE {r['mape']:.1%}  bias {r['bias']:+.1%}")
    print(f"P10–P90 coverage {d['interval_coverage']:.0%} over {d['backtest_quarters']} quarters → {a.out}/index.html")


if __name__ == "__main__":
    main()
