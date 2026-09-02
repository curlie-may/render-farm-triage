#!/usr/bin/env python3
"""One-off loader: pushes the generated Parquet files into the existing
ClickHouse Cloud tables (render_task_attempts, farm_nodes, past_incidents).

The tables already exist per db/schema.sql. This script never creates, drops,
or alters a table — it only truncates (to make itself safely re-runnable) and
inserts.

Usage:
    python load.py            # truncate + load all three tables
    python load.py --dry-run  # read Parquet, report counts/dtypes, no writes
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

TABLE_SPECS = [
    ("data/attempts.parquet", "render_task_attempts"),
    ("data/farm_nodes.parquet", "farm_nodes"),
    ("data/past_incidents.parquet", "past_incidents"),
]


def prepare_attempts(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # duration_sec is MATERIALIZED in ClickHouse; it is not a column we insert.
    if "duration_sec" in df.columns:
        df = df.drop(columns=["duration_sec"])

    # started_at / ended_at: DateTime is second resolution in the DDL. pandas
    # reads Parquet timestamps as datetime64[ns]; cast down to [s] so
    # clickhouse-connect writes whole seconds rather than choking on
    # sub-second precision it has nowhere to put.
    df["started_at"] = pd.to_datetime(df["started_at"]).astype("datetime64[s]")
    df["ended_at"] = pd.to_datetime(df["ended_at"]).astype("datetime64[s]")

    # error_class / error_text are Nullable(String). Parquet already stores
    # missing values as None on success rows; make sure NaN (if any slipped
    # in via a different null representation) also becomes None, not "".
    df["error_class"] = df["error_class"].where(df["error_class"].notna(), None)
    df["error_text"] = df["error_text"].where(df["error_text"].notna(), None)

    # asset_refs is Array(String). Parquet round-trips this as a numpy
    # ndarray per row; clickhouse-connect wants a plain Python list.
    df["asset_refs"] = df["asset_refs"].apply(
        lambda x: list(x) if x is not None else []
    )

    df["uses_hair_shader"] = df["uses_hair_shader"].astype(bool)

    return df


def prepare_farm_nodes(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["online"] = df["online"].astype(bool)
    return df


def prepare_past_incidents(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # occurred_on is Date, not DateTime. Parquet stores it as an ISO date
    # string (object dtype); convert to Python date objects.
    df["occurred_on"] = pd.to_datetime(df["occurred_on"]).dt.date
    return df


PREPARERS = {
    "render_task_attempts": prepare_attempts,
    "farm_nodes": prepare_farm_nodes,
    "past_incidents": prepare_past_incidents,
}


def get_client():
    import clickhouse_connect

    host = os.environ["CLICKHOUSE_HOST"]
    user = os.environ["CLICKHOUSE_USER"]
    password = os.environ["CLICKHOUSE_PASSWORD"]
    database = os.environ["CLICKHOUSE_DATABASE"]
    return clickhouse_connect.get_client(
        host=host, username=user, password=password, database=database, secure=True,
    )


def load_table(client, parquet_path: str, table: str, dry_run: bool) -> bool:
    print(f"\n=== {table}  <-  {parquet_path} ===")
    if not os.path.exists(parquet_path):
        print(f"  SKIP: {parquet_path} not found")
        return False

    df_raw = pd.read_parquet(parquet_path)
    preparer = PREPARERS.get(table)
    df = preparer(df_raw) if preparer else df_raw.copy()

    print(f"  Parquet rows: {len(df)}")
    print("  Parquet dtypes:")
    for col, dt in df.dtypes.items():
        print(f"    {col}: {dt}")

    current_count = int(client.command(f"SELECT count() FROM {table}"))
    print(f"  Current row count in ClickHouse: {current_count}")

    if dry_run:
        print("  --dry-run: no truncate, no insert performed.")
        return True

    if current_count > 0:
        print(f"  Truncating {table} ({current_count} rows being removed)...")
        client.command(f"TRUNCATE TABLE {table}")

    try:
        client.insert_df(table, df)
    except Exception as exc:
        print(f"  INSERT FAILED for table '{table}'")
        print(f"  Error: {exc}")
        raise

    after_count = int(client.command(f"SELECT count() FROM {table}"))
    print(f"  Row count after insert: {after_count}")
    if after_count != len(df):
        raise AssertionError(
            f"Row count mismatch after insert into {table}: "
            f"expected {len(df)} (from DataFrame), got {after_count} (in ClickHouse)"
        )
    print(f"  OK: inserted row count matches DataFrame row count ({after_count}).")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Load generated Parquet files into the existing ClickHouse Cloud tables."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Read Parquet and report counts/dtypes only; no truncate, no insert.",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    load_dotenv(base_dir / ".env")

    required = ["CLICKHOUSE_HOST", "CLICKHOUSE_USER", "CLICKHOUSE_PASSWORD", "CLICKHOUSE_DATABASE"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)

    client = get_client()

    all_ok = True
    for rel_path, table in TABLE_SPECS:
        parquet_path = str(base_dir / rel_path)
        result = load_table(client, parquet_path, table, args.dry_run)
        all_ok = all_ok and result

    print()
    if args.dry_run:
        print("DRY RUN COMPLETE" if all_ok else "DRY RUN COMPLETE WITH SKIPPED TABLES")
    else:
        print("LOAD COMPLETE" if all_ok else "LOAD INCOMPLETE (see SKIP lines above)")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
