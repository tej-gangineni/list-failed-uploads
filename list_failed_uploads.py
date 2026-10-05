#!/usr/bin/env python
"""List failed file uploads: filename, uploaded time, uploaded by.

Read-only. A file counts as failed the same way the files UI decides it:
`processing_completed` is False and the upload is older than the grace
window (default 20 min, anything newer is still "processing"), or ARAI
reported `arai_status == "failed"`.

Requirements (env, loaded from cpod-core/.env):
- Mongo: DB_URL, DB_NAME (or MONGODB_URL/MONGODB_DATABASE)

Usage:
    python scripts/list_failed_uploads.py
    python scripts/list_failed_uploads.py --since-days 7
    python scripts/list_failed_uploads.py --csv failed_uploads.csv
"""

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

# load DB_URL/DB_NAME from cpod-core/.env regardless of the cwd
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv()

COLUMNS = ["filename", "uploaded_time", "uploaded_by", "uploaded_by_email"]


def get_mongo_config() -> tuple[str, str]:
    """Return (url, database name) from the environment."""
    db_url = os.getenv("DB_URL") or os.getenv("MONGODB_URL")
    db_name = os.getenv("DB_NAME") or os.getenv("MONGODB_DATABASE")
    if not db_url or not db_name:
        raise ValueError(
            "Set DB_URL/DB_NAME (or MONGODB_URL/MONGODB_DATABASE)."
        )
    return db_url, db_name


def build_query(
    grace_minutes: int, since_days: int | None, include_deleted: bool
) -> dict[str, Any]:
    """Build the files query matching the UI's notion of a failed upload."""
    now = datetime.now(timezone.utc)
    query: dict[str, Any] = {
        "$or": [
            {
                "processing_completed": False,
                "uploaded_first_time": {
                    "$lt": now - timedelta(minutes=grace_minutes)
                },
            },
            {"arai_status": "failed"},
        ]
    }
    if since_days is not None:
        query["uploaded_first_time"] = {
            "$gte": now - timedelta(days=since_days)
        }
    if not include_deleted:
        query["deleted"] = {"$ne": True}
    return query


def load_users(db: Database, user_ids: set[str]) -> dict[str, dict[str, Any]]:
    """Map str(user _id) -> user doc; _id may be stored as str or ObjectId."""
    ids: list[Any] = list(user_ids)
    ids += [ObjectId(uid) for uid in user_ids if ObjectId.is_valid(uid)]
    users = db.get_collection("users").find(
        {"_id": {"$in": ids}}, {"full_name": 1, "email": 1}
    )
    return {str(user["_id"]): user for user in users}


def format_time(value: Any) -> str:
    """Render a Mongo datetime as a UTC string."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return str(value or "")


def collect_rows(db: Database, query: dict[str, Any]) -> list[dict[str, str]]:
    """Fetch matching files and resolve each uploader to a name/email."""
    files = list(
        db.get_collection("files")
        .find(
            query,
            {
                "filename": 1,
                "uploaded_first_time": 1,
                "uploaded_by_user_id": 1,
            },
        )
        .sort("uploaded_first_time", -1)
    )
    users = load_users(
        db,
        {
            str(f["uploaded_by_user_id"])
            for f in files
            if f.get("uploaded_by_user_id")
        },
    )

    rows = []
    for f in files:
        user_id = str(f.get("uploaded_by_user_id") or "")
        user = users.get(user_id, {})
        rows.append(
            {
                "filename": f.get("filename") or "",
                "uploaded_time": format_time(f.get("uploaded_first_time")),
                # fall back to the raw id when the user no longer exists
                "uploaded_by": user.get("full_name")
                or user.get("email")
                or user_id,
                "uploaded_by_email": user.get("email") or "",
            }
        )
    return rows


def print_table(rows: list[dict[str, str]]) -> None:
    """Print rows as an aligned text table."""
    widths = {
        col: max(len(col), *(len(row[col]) for row in rows)) for col in COLUMNS
    }
    print("  ".join(col.upper().ljust(widths[col]) for col in COLUMNS))
    print("  ".join("-" * widths[col] for col in COLUMNS))
    for row in rows:
        print("  ".join(row[col].ljust(widths[col]) for col in COLUMNS))


def main() -> int:
    """Parse args, query Mongo and print or export the failed uploads."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--since-days",
        type=int,
        default=None,
        help="Only uploads from the last N days (default: all time)",
    )
    parser.add_argument(
        "--grace-minutes",
        type=int,
        default=20,
        help="Uploads newer than this are still processing (default: 20)",
    )
    parser.add_argument(
        "--include-deleted",
        action="store_true",
        help="Include files marked deleted",
    )
    parser.add_argument(
        "--csv", metavar="PATH", help="Write results to a CSV file"
    )
    args = parser.parse_args()

    db_url, db_name = get_mongo_config()
    client: MongoClient = MongoClient(db_url, serverSelectionTimeoutMS=10000)
    try:
        rows = collect_rows(
            client[db_name],
            build_query(
                args.grace_minutes, args.since_days, args.include_deleted
            ),
        )
    finally:
        client.close()

    if not rows:
        print("No failed uploads found.")
        return 0

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote {len(rows)} failed uploads to {args.csv}")
    else:
        print_table(rows)
        print(f"\n{len(rows)} failed uploads")
    return 0


if __name__ == "__main__":
    sys.exit(main())
