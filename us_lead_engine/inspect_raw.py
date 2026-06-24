# us_lead_engine/inspect_raw.py
# Throwaway: prints the raw JSON of the first search result so we can map fields
# correctly. Search is free (0 credits). Run: python -m us_lead_engine.inspect_raw

import json

from .config import ICP_QUERY
from . import apollo_client

people, total = apollo_client.search({**ICP_QUERY, "per_page": 2}, page=1)
print(f"TOTAL MATCHES: {total} | returned this page: {len(people)}\n")

if people:
    print("=== RAW FIRST PERSON ===")
    print(json.dumps(people[0], indent=2))
    print("\n=== ORG KEYS ON FIRST PERSON ===")
    org = people[0].get("organization") or {}
    print(list(org.keys()))
