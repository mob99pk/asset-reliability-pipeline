"""Smoke test: connect to Snowflake as the service user via key-pair auth.

Usage: python scripts/check_connection.py
"""
import os
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def get_connection(schema: str | None = None):
    """Open a Snowflake connection from SNOWFLAKE_* env vars (key-pair auth)."""
    key_path = Path(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"])
    if not key_path.is_absolute():
        key_path = ROOT / key_path
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        authenticator="SNOWFLAKE_JWT",
        private_key_file=str(key_path),
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=schema,
    )


if __name__ == "__main__":
    with get_connection() as conn:
        row = conn.cursor().execute(
            "select current_user(), current_role(), current_warehouse(), "
            "current_database(), current_version()"
        ).fetchone()
    print("user={} role={} warehouse={} database={} version={}".format(*row))
