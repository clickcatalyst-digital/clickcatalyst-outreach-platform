# scripts/backfill_pixel_check.py
# One-time enrichment of existing Places leads with pixel data.
# Skips leads already checked. Quality threshold from PIXEL_CHECK_MIN_QUALITY env (default 40).

import sys
import time
sys.path.insert(0, ".")

from api.services.pixel_service import check_places_leads_batch, PIXEL_CHECK_MIN_QUALITY


def main():
    print(f"\n🔍 Pixel Backfill — Places Leads")
    print(f"   Quality threshold: {PIXEL_CHECK_MIN_QUALITY} (override via PIXEL_CHECK_MIN_QUALITY env)")
    print(f"   Concurrency: 10 parallel checks\n")

    start = time.time()
    summary = check_places_leads_batch(max_workers=10, only_unchecked=True)
    elapsed = time.time() - start

    print(f"\n{'='*60}")
    print(f"✨ Backfill complete in {elapsed:.1f}s")
    print(f"   Total checked:   {summary['total']}")
    print(f"   ✅ Has pixel:    {summary['found']}")
    print(f"   ❌ No pixel:     {summary['not_found']}")
    print(f"   ⚠️  Unreachable: {summary['failed']} (will retry on next force-recheck)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()