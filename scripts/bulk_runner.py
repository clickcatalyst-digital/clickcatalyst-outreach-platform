# scripts/bulk_runner.py
# Bulk Places API runner: cartesian product of cities x query templates.
# Idempotent (existing leads get refreshed, not duplicated).

import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, ".")  # so we can import api.*

from api.database import get_conn
from api.services.places_service import search_text, normalize_place
from api.routes.places import _upsert_places_lead, _upsert_enrichment


# --- Helpers -------------------------------------------------------------

def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text())


def existing_place_ids(cursor) -> set[str]:
    cursor.execute("SELECT Place_ID FROM places_leads")
    return {r["Place_ID"] for r in cursor.fetchall()}


def start_run(cursor, config_name: str, total_queries: int) -> int:
    cursor.execute("""
        INSERT INTO bulk_run_history (Config_Name, Total_Queries, Status)
        VALUES (?, ?, 'running')
    """, (config_name, total_queries))
    return cursor.lastrowid


def finish_run(cursor, run_id: int, successful: int, failed: int,
               total_leads: int, new_leads: int, status: str = "done",
               error_log: str = None):
    cursor.execute("""
        UPDATE bulk_run_history
        SET Finished_At = CURRENT_TIMESTAMP,
            Successful = ?, Failed = ?,
            Total_Leads = ?, New_Leads = ?,
            Status = ?, Error_Log = ?
        WHERE Run_ID = ?
    """, (successful, failed, total_leads, new_leads, status, error_log, run_id))


def log_query_result(cursor, run_id: int, query: str, city: str,
                     status: str, leads_returned: int, leads_new: int,
                     error: str = None):
    cursor.execute("""
        INSERT INTO bulk_run_queries
            (Run_ID, Query_Text, City, Status, Leads_Returned, Leads_New, Error, Executed_At)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (run_id, query, city, status, leads_returned, leads_new, error))


# --- Core runner ---------------------------------------------------------

def run_query_with_retry(query: str, location_bias: dict,
                         max_results: int, max_retries: int) -> dict:
    """Returns places list. Raises on final failure."""
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            return search_text(
                query=query,
                location_bias=location_bias,
                max_results=max_results,
            )
        except Exception as e:
            last_err = e
            wait = 2 ** attempt   # 2s, 4s, 8s
            print(f"      ⚠️  attempt {attempt}/{max_retries} failed: {e}. Retrying in {wait}s...")
            time.sleep(wait)
    raise last_err


def expand_queries(config: dict, cities: dict) -> list[dict]:
    """Cartesian product: cities x query_templates."""
    plan = []
    for city_key in config["cities"]:
        city = cities[city_key]
        for template in config["query_templates"]:
            plan.append({
                "query": template.format(city=city["name"]),
                "city_name": city["name"],
                "city_key": city_key,
                "location_bias": {
                    "lat": city["lat"],
                    "lng": city["lng"],
                    "radius_m": city["radius_m"],
                },
            })
    return plan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to config JSON")
    parser.add_argument("--cities", default="configs/cities.json", help="Path to cities JSON")
    parser.add_argument("--execute", action="store_true",
                        help="Actually run the API calls. Without this, dry-run only.")
    parser.add_argument("--max-results", type=int, default=None,
                        help="Override max_results_per_query from config")
    args = parser.parse_args()

    config = load_json(args.config)
    cities = load_json(args.cities)

    plan = expand_queries(config, cities)
    max_results = args.max_results or config.get("max_results_per_query", 20)
    delay      = config.get("delay_between_calls_seconds", 1)
    retries    = config.get("max_retries_per_query", 3)

    # --- Dry run summary -------------------------------------------------
    print(f"\n📋 Plan: {len(plan)} searches ({len(config['cities'])} cities × {len(config['query_templates'])} templates)")
    print(f"   Max results per query: {max_results}")
    print(f"   Estimated leads: ~{len(plan) * max_results}")
    print(f"   Estimated cost: $0.00 (within free 5,000/month Pro tier)")
    print(f"   Estimated runtime: ~{len(plan) * (delay + 1)}s\n")

    print("Queries to run:")
    for i, p in enumerate(plan, 1):
        print(f"   [{i:>3}] {p['query']}")

    if not args.execute:
        print("\n💡 Dry run only. Add --execute to actually run.\n")
        return

    # --- Execute ---------------------------------------------------------
    print(f"\n🚀 Executing {len(plan)} searches...\n")

    conn = get_conn()
    cursor = conn.cursor()

    before = existing_place_ids(cursor)
    print(f"   Starting with {len(before)} existing leads in DB\n")

    run_id = start_run(cursor, config["name"], len(plan))
    conn.commit()

    successful = failed = 0
    total_leads = total_new = 0
    errors_log = []

    for i, p in enumerate(plan, 1):
        prefix = f"[{i:>3}/{len(plan)}] {p['query']}"
        print(f"{prefix:.<80}", end=" ", flush=True)

        try:
            result = run_query_with_retry(
                query=p["query"],
                location_bias=p["location_bias"],
                max_results=max_results,
                max_retries=retries,
            )
            places = result["places"]
            leads_returned = len(places)
            leads_new = 0

            for raw_place in places:
                normalized = normalize_place(raw_place)
                if not normalized:
                    continue
                if normalized["place_id"] not in before:
                    leads_new += 1
                    before.add(normalized["place_id"])
                _upsert_places_lead(cursor, normalized, source_query=p["query"])
                _upsert_enrichment(cursor, normalized)

            conn.commit()
            log_query_result(cursor, run_id, p["query"], p["city_name"],
                             "success", leads_returned, leads_new)
            conn.commit()

            successful += 1
            total_leads += leads_returned
            total_new += leads_new
            print(f"✅ {leads_returned} ({leads_new} new)")

        except Exception as e:
            failed += 1
            err_msg = str(e)[:200]
            errors_log.append(f"[{p['query']}] {err_msg}")
            log_query_result(cursor, run_id, p["query"], p["city_name"],
                             "failed", 0, 0, error=err_msg)
            conn.commit()
            print(f"❌ {err_msg[:50]}")

        time.sleep(delay)

    finish_run(cursor, run_id, successful, failed,
               total_leads, total_new,
               status="done" if failed == 0 else "done_with_errors",
               error_log="\n".join(errors_log) if errors_log else None)
    conn.commit()
    conn.close()

    # --- Summary ---------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"✨ Run complete: {successful}/{len(plan)} successful, {failed} failed")
    print(f"   Total leads returned: {total_leads}")
    print(f"   New unique leads:     {total_new}")
    print(f"   Updated existing:     {total_leads - total_new}")
    print(f"   Run ID: {run_id} (query: SELECT * FROM bulk_run_history WHERE Run_ID={run_id})")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()