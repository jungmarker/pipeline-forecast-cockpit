"""Open a Ledgerly DuckDB file read-only and create the analysis views in memory."""
from importlib.resources import files

import duckdb

RAW_TABLES = ("opportunities", "accounts", "opportunity_stage_history", "users")


def connect(db_path: str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"attach '{db_path}' as src (read_only)")
    con.execute("create schema raw")
    for t in RAW_TABLES:
        con.execute(f"create view raw.{t} as select * from src.raw.{t}")
    con.execute(sql("opps"))
    return con


def sql(name: str, **params) -> str:
    text = files("cockpit").joinpath(f"sql/{name}.sql").read_text()
    return text.format(**params) if params else text


def has_truth(con) -> bool:
    return bool(con.execute("select count(*) from duckdb_tables() where database_name = 'src' "
                            "and schema_name = 'truth' and table_name = 'open_opportunity_outcomes'").fetchone()[0])
