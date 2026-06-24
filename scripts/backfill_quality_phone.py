# scripts/backfill_quality_phone.py
# One-shot backfill: compute quality_score + phone_formatted for existing places_leads.

import sys
sys.path.insert(0, ".")  # so we can import api.*

from api.database import get_conn
from api.services.lead_quality import score_lead, format_phone


def main():
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT Place_ID, CIN, Display_Name, Primary_Type, Types_JSON,
               User_Rating_Count, National_Phone, International_Phone
        FROM places_leads
        WHERE Quality_Score = 0 OR Quality_Score IS NULL
    """)
    rows = cursor.fetchall()
    print(f"Backfilling {len(rows)} rows...")

    for r in rows:
        score, reasons = score_lead(
            r["Display_Name"], r["Primary_Type"], r["Types_JSON"], r["User_Rating_Count"]
        )
        phone = format_phone(r["National_Phone"] or r["International_Phone"])

        cursor.execute("""
            UPDATE places_leads
            SET Quality_Score = ?, Quality_Reasons = ?, Phone_Formatted = ?
            WHERE Place_ID = ?
        """, (score, reasons, phone, r["Place_ID"]))

        cursor.execute("""
            UPDATE company_enrichment
            SET Phone_Formatted = ?
            WHERE CIN = ?
        """, (phone, r["CIN"]))

    conn.commit()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()