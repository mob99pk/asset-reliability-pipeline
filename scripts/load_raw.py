"""Load data/ source files into ASSET_RELIABILITY.RAW.

Full reload, safe to re-run: PUT to an internal stage, TRUNCATE, then
COPY ... FORCE = TRUE. Everything lands as VARCHAR / VARIANT; typing and
cleaning happen in dbt.

Usage: python scripts/load_raw.py
"""
from check_connection import ROOT, get_connection

DATA = ROOT / "data"

SETUP = [
    "create stage if not exists landing comment = 'Landing zone for source files'",
    """create or replace file format csv_fmt
         type = csv skip_header = 1 field_optionally_enclosed_by = '"'
         empty_field_as_null = true""",
    "create or replace file format json_fmt type = json strip_outer_array = true",
    """create table if not exists work_orders (
         wo_id varchar, asset_id varchar, type varchar, priority varchar,
         raised_date varchar, due_date varchar, completed_date varchar, status varchar,
         _source_file varchar, _row_number number, _loaded_at timestamp_ltz)""",
    """create table if not exists assets (
         raw variant,
         _source_file varchar, _row_number number, _loaded_at timestamp_ltz)""",
]

# table -> (source file, COPY statement). The transforming SELECT adds lineage
# columns; FORCE = TRUE overrides Snowflake's 64-day "already loaded" skip.
LOADS = {
    "work_orders": ("work_orders.csv", """
        copy into work_orders (wo_id, asset_id, type, priority, raised_date, due_date,
                               completed_date, status, _source_file, _row_number, _loaded_at)
        from (select $1, $2, $3, $4, $5, $6, $7, $8,
                     metadata$filename, metadata$file_row_number, current_timestamp()
              from @landing/work_orders/)
        file_format = (format_name = csv_fmt)
        force = true"""),
    "assets": ("assets.json", """
        copy into assets (raw, _source_file, _row_number, _loaded_at)
        from (select $1, metadata$filename, metadata$file_row_number, current_timestamp()
              from @landing/assets/)
        file_format = (format_name = json_fmt)
        force = true"""),
}


def main():
    with get_connection(schema="RAW") as conn:
        cur = conn.cursor()
        for sql in SETUP:
            cur.execute(sql)

        for table, (filename, copy_sql) in LOADS.items():
            path = (DATA / filename).as_posix()
            cur.execute(f"put 'file://{path}' @landing/{table}/ auto_compress = true overwrite = true")
            cur.execute(f"truncate table {table}")
            cur.execute(copy_sql)
            cols = [c[0].lower() for c in cur.description]
            for row in cur.fetchall():
                r = dict(zip(cols, row))
                print(f"{table}: {r['file']} status={r['status']} "
                      f"rows_loaded={r['rows_loaded']} errors={r['errors_seen']}")
            count = cur.execute(f"select count(*) from {table}").fetchone()[0]
            print(f"  -> RAW.{table.upper()} now has {count} rows")


if __name__ == "__main__":
    main()
