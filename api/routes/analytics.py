# ─────────────────────────────────────────────
# api/routes/analytics.py
# ─────────────────────────────────────────────
from fastapi import APIRouter
from fastapi.responses import Response, RedirectResponse
from typing import Optional
from ..database import get_conn, country_filter

router = APIRouter()

@router.get("/overview")
def get_overview(country: Optional[str] = None):
    conn = get_conn()
    cursor = conn.cursor()
    flt = country_filter(country, "CIN", "Batch_ID")

    def q(extra=""):
        cursor.execute(f"SELECT COUNT(*) FROM outreach_analytics WHERE 1=1 {flt} {extra}")
        return cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(DISTINCT CIN) FROM outreach_analytics WHERE 1=1 {flt}")
    unique_companies = cursor.fetchone()[0]

    data = {
        "total_sent":       q(),
        "total_clicked":    q("AND Audit_Link_Clicked = 1"),
        "total_opened":     q("AND Email_Opened = 1"),
        "click_rate":       0,
        "open_rate":        0,
        "unique_companies": unique_companies,
        "total_replied":    q("AND Reply_Received = 1"),
        "reply_rate":       0,
    }

    if data["total_sent"] > 0:
        data["click_rate"] = round(data["total_clicked"] / data["total_sent"] * 100, 1)
        data["open_rate"]  = round(data["total_opened"]  / data["total_sent"] * 100, 1)
        data["reply_rate"] = round(data["total_replied"] / data["total_sent"] * 100, 1)

    conn.close()
    return data


@router.get("/by-variant")
def get_by_variant(country: Optional[str] = None):
    conn = get_conn()
    cursor = conn.cursor()
    flt = country_filter(country, "CIN", "Batch_ID")
    cursor.execute(f"""
        SELECT
            Campaign_Variant,
            COUNT(*) AS sent,
            SUM(CASE WHEN Audit_Link_Clicked = 1 THEN 1 ELSE 0 END) AS clicked,
            SUM(CASE WHEN Email_Opened = 1 THEN 1 ELSE 0 END) AS opened,
            ROUND(100.0 * SUM(CASE WHEN Audit_Link_Clicked = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS click_rate,
            ROUND(100.0 * SUM(CASE WHEN Email_Opened = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS open_rate
        FROM outreach_analytics
        WHERE Campaign_Variant IS NOT NULL {flt}
        GROUP BY Campaign_Variant
        ORDER BY click_rate DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


@router.get("/by-batch")
def get_by_batch(country: Optional[str] = None):
    conn = get_conn()
    cursor = conn.cursor()
    flt = country_filter(country, "CIN", "Batch_ID")
    cursor.execute(f"""
        SELECT
            Batch_ID,
            COUNT(*) AS sent,
            SUM(CASE WHEN Audit_Link_Clicked = 1 THEN 1 ELSE 0 END) AS clicked,
            MIN(Email_Sent_Date) AS sent_date
        FROM outreach_analytics
        WHERE 1=1 {flt}
        GROUP BY Batch_ID
        ORDER BY sent_date DESC
        LIMIT 20
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


@router.get("/timeline")
def get_timeline(country: Optional[str] = None):
    """Daily send + click counts for the last 30 days."""
    conn = get_conn()
    cursor = conn.cursor()
    flt = country_filter(country, "CIN", "Batch_ID")
    cursor.execute(f"""
        SELECT
            Email_Sent_Date AS date,
            COUNT(*) AS sent,
            SUM(CASE WHEN Audit_Link_Clicked = 1 THEN 1 ELSE 0 END) AS clicked
        FROM outreach_analytics
        WHERE Email_Sent_Date >= date('now', '-30 days') {flt}
        GROUP BY Email_Sent_Date
        ORDER BY Email_Sent_Date ASC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


@router.get("/ab-tests")
def get_ab_tests(country: Optional[str] = None):
    """Groups variants into A/B pairs with statistical comparison."""
    conn = get_conn()
    cursor = conn.cursor()
    flt = country_filter(country, "CIN", "Batch_ID")
    cursor.execute(f"""
        SELECT
            Campaign_Variant,
            COUNT(*) AS sent,
            SUM(CASE WHEN Audit_Link_Clicked = 1 THEN 1 ELSE 0 END) AS clicked,
            SUM(CASE WHEN Email_Opened = 1 THEN 1 ELSE 0 END) AS opened
        FROM outreach_analytics
        WHERE Campaign_Variant IS NOT NULL {flt}
        GROUP BY Campaign_Variant
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # Group into A/B pairs by stripping _a/_b suffix
    pairs = {}
    for r in rows:
        key = r['Campaign_Variant']
        if key.endswith('_a') or key.endswith('_b'):
            base = key[:-2]
            side = key[-1]
        else:
            base = key
            side = 'a'
        if base not in pairs:
            pairs[base] = {'base': base, 'a': None, 'b': None}
        pairs[base][side] = {
            'variant': key,
            'sent': r['sent'],
            'clicked': r['clicked'],
            'opened': r['opened'],
            'click_rate': round(100.0 * r['clicked'] / r['sent'], 1) if r['sent'] > 0 else 0,
            'open_rate': round(100.0 * r['opened'] / r['sent'], 1) if r['sent'] > 0 else 0,
        }

    # Compute z-test for each pair
    import math
    results = []
    for base, pair in pairs.items():
        a = pair.get('a')
        b = pair.get('b')
        test = {
            'base': base,
            'a': a,
            'b': b,
            'winner': None,
            'significant': False,
            'p_value': None,
            'min_sample': None,
        }

        if a and b and a['sent'] >= 5 and b['sent'] >= 5:
            n_a, n_b = a['sent'], b['sent']
            p_a = a['clicked'] / n_a
            p_b = b['clicked'] / n_b
            p_pool = (a['clicked'] + b['clicked']) / (n_a + n_b)

            if p_pool > 0 and p_pool < 1:
                se = math.sqrt(p_pool * (1 - p_pool) * (1/n_a + 1/n_b))
                if se > 0:
                    z = (p_a - p_b) / se
                    # Two-tailed p-value approximation
                    p_val = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
                    test['p_value'] = round(p_val, 4)
                    test['significant'] = p_val < 0.05
                    test['winner'] = 'a' if p_a > p_b else 'b' if p_b > p_a else None

            # Minimum sample estimate (80% power, 5% significance, detect 5pp difference)
            if p_pool > 0 and p_pool < 1:
                effect = 0.05
                z_alpha = 1.96
                z_beta = 0.84
                min_n = ((z_alpha + z_beta) ** 2 * 2 * p_pool * (1 - p_pool)) / (effect ** 2)
                test['min_sample'] = int(math.ceil(min_n))

        results.append(test)

    return results


@router.get("/track/open")
def track_open(aid: int):
    """1x1 transparent pixel — records email open."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE outreach_analytics
        SET Email_Opened = 1, Opened_At = CURRENT_TIMESTAMP
        WHERE Analytics_ID = ? AND (Email_Opened IS NULL OR Email_Opened = 0)
    """, (aid,))
    conn.commit()
    conn.close()

    # Return 1x1 transparent GIF
    pixel = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'
    return Response(content=pixel, media_type="image/gif",
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@router.get("/track/click")
def track_click(aid: int, url: str = ""):
    """Click tracking — records audit link click and redirects."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE outreach_analytics
        SET Audit_Link_Clicked = 1, Clicked_At = CURRENT_TIMESTAMP
        WHERE Analytics_ID = ? AND (Audit_Link_Clicked IS NULL OR Audit_Link_Clicked = 0)
    """, (aid,))
    conn.commit()
    conn.close()

    redirect_url = url if url else "https://clickcatalyst.digital/free-audit"
    return RedirectResponse(url=redirect_url)


@router.get("/unsubscribe")
def unsubscribe(cin: str):
    """Marks a lead as unsubscribed."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE company_enrichment
        SET Unsubscribed = 1, Unsubscribed_Date = CURRENT_DATE,
            Pipeline_Status = 'Unsubscribed'
        WHERE CIN = ?
    """, (cin,))
    conn.commit()
    conn.close()

    return Response(
        content="""<html><body style="font-family:Georgia,serif;text-align:center;padding:60px;">
        <h2>You've been unsubscribed</h2>
        <p style="color:#666;">You won't receive any more emails from us.</p>
        </body></html>""",
        media_type="text/html"
    )

# @router.get("/scheduler")
# def get_scheduler_status():
#     """Returns scheduling info for the dashboard."""
#     conn = get_conn()
#     cursor = conn.cursor()

#     # Warmup day
#     cursor.execute("SELECT MIN(Email_Sent_Date) FROM outreach_analytics")
#     first_send = cursor.fetchone()[0]
#     warmup_day = 0
#     if first_send:
#         from datetime import date as d
#         first_date = d.fromisoformat(first_send)
#         warmup_day = (d.today() - first_date).days

#     # Daily limit based on warmup
#     schedule = [(0,3,5),(4,7,10),(8,14,20),(15,21,35),(22,30,50),(31,60,75),(61,999,100)]
#     daily_limit = 5
#     for start, end, limit in schedule:
#         if start <= warmup_day <= end:
#             daily_limit = limit
#             break

#     # Sent today
#     cursor.execute("SELECT COUNT(*) FROM outreach_analytics WHERE Email_Sent_Date = date('now')")
#     sent_today = cursor.fetchone()[0]

#     # Sent this week
#     cursor.execute("SELECT COUNT(*) FROM outreach_analytics WHERE Email_Sent_Date >= date('now', '-7 days')")
#     sent_week = cursor.fetchone()[0]

#     # By hour performance
#     cursor.execute("""
#         SELECT Send_Hour, COUNT(*) as sent,
#             SUM(CASE WHEN Email_Opened = 1 THEN 1 ELSE 0 END) as opened,
#             SUM(CASE WHEN Audit_Link_Clicked = 1 THEN 1 ELSE 0 END) as clicked,
#             SUM(CASE WHEN Reply_Received = 1 THEN 1 ELSE 0 END) as replied
#         FROM outreach_analytics WHERE Send_Hour IS NOT NULL
#         GROUP BY Send_Hour ORDER BY Send_Hour
#     """)
#     by_hour = [dict(r) for r in cursor.fetchall()]

#     # By day performance
#     cursor.execute("""
#         SELECT Send_DayOfWeek, COUNT(*) as sent,
#             SUM(CASE WHEN Email_Opened = 1 THEN 1 ELSE 0 END) as opened,
#             SUM(CASE WHEN Audit_Link_Clicked = 1 THEN 1 ELSE 0 END) as clicked,
#             SUM(CASE WHEN Reply_Received = 1 THEN 1 ELSE 0 END) as replied
#         FROM outreach_analytics WHERE Send_DayOfWeek IS NOT NULL
#         GROUP BY Send_DayOfWeek ORDER BY Send_DayOfWeek
#     """)
#     by_day = [dict(r) for r in cursor.fetchall()]

#     # Queue size
#     cursor.execute("""
#         SELECT COUNT(*) FROM vw_qualified_leads q
#         JOIN company_enrichment e ON q.CIN = e.CIN
#         JOIN company_contacts cc ON q.CIN = cc.CIN AND cc.Is_Primary_Contact = 1
#         WHERE e.Pipeline_Status = 'Intelligence_Ready'
#         AND (e.Unsubscribed IS NULL OR e.Unsubscribed = 0)
#     """)
#     queue_size = cursor.fetchone()[0]

#     import datetime as dt
#     now = dt.datetime.now()
#     hour = now.hour
#     dow = now.weekday()

#     # Load schedule config
#     cursor2 = get_conn().cursor()
#     cursor2.execute("SELECT Config_Key, Config_Value FROM scheduler_config")
#     config = {row[0]: row[1] for row in cursor2.fetchall()}

#     start_h = int(config.get('start_hour', '9'))
#     end_h = int(config.get('end_hour', '17'))
#     peak = [int(x) for x in config.get('peak_hours', '10,11,14,15').split(',') if x.strip()]
#     send_days = [int(x) for x in config.get('send_days', '0,1,2,3,4').split(',') if x.strip()]

#     is_send_day = dow in send_days
#     is_business_hours = start_h <= hour < end_h
#     is_peak = hour in peak

#     conn.close()

#     return {
#         "warmup_day": warmup_day,
#         "daily_limit": daily_limit,
#         "sent_today": sent_today,
#         "sent_week": sent_week,
#         "remaining": max(0, daily_limit - sent_today),
#         "queue_size": queue_size,
#         "next_up": next_up,
#         "current_hour": hour,
#         "current_day": dow,
#         "is_weekend": not is_send_day,
#         "is_business_hours": is_business_hours,
#         "is_peak": is_peak,
#         "can_send": is_business_hours and is_send_day and sent_today < daily_limit and queue_size > 0,
#         "config": {
#             "start_hour": start_h,
#             "end_hour": end_h,
#             "peak_hours": peak,
#             "send_days": send_days,
#         },
#     }


@router.get("/bayesian")
def get_bayesian_status(country: Optional[str] = None):
    """Returns Bayesian model state for the dashboard."""
    import json, os, math

    conn = get_conn()
    cursor = conn.cursor()
    flt = country_filter(country, "CIN", "Batch_ID")

    # Thompson Sampling posteriors
    cursor.execute(f"""
        SELECT Campaign_Variant, COUNT(*) as total,
            SUM(CASE WHEN Audit_Link_Clicked = 1 THEN 1 ELSE 0 END) as clicked,
            SUM(CASE WHEN Reply_Received = 1 THEN 1 ELSE 0 END) as replied,
            SUM(CASE WHEN Converted = 1 THEN 1 ELSE 0 END) as converted
        FROM outreach_analytics
        WHERE Campaign_Variant IS NOT NULL {flt}
        GROUP BY Campaign_Variant
    """)
    variants = []
    for row in cursor.fetchall():
        r = dict(row)
        alpha = 1 + r['clicked']
        beta = 1 + (r['total'] - r['clicked'])
        mean = alpha / (alpha + beta)
        variants.append({
            **r,
            'alpha': alpha,
            'beta': beta,
            'mean': round(mean, 4),
            'ci_low': round(max(0, mean - 1.96 * math.sqrt(mean*(1-mean)/max(r['total'],1))), 4),
            'ci_high': round(min(1, mean + 1.96 * math.sqrt(mean*(1-mean)/max(r['total'],1))), 4),
        })

    # Deliverability state
    model_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'bayesian_model_state.json')
    deliverability = {"reputation": 0.7, "trend": "no_data", "history": []}
    if os.path.exists(model_file):
        try:
            with open(model_file) as f:
                state = json.load(f)
                deliverability = {
                    "reputation": state.get("reputation", 0.7),
                    "trend": "stable",
                    "history": state.get("history", [])[-14:],
                }
                if len(deliverability["history"]) >= 3:
                    recent = [h["reputation"] for h in deliverability["history"][-5:]]
                    older = [h["reputation"] for h in deliverability["history"][-10:-5]]
                    if older:
                        diff = sum(recent)/len(recent) - sum(older)/len(older)
                        deliverability["trend"] = "improving" if diff > 0.05 else "declining" if diff < -0.05 else "stable"
        except Exception:
            pass

    # Reply stats
    cursor.execute(f"""
        SELECT COUNT(*) as total_replies,
            COUNT(DISTINCT CIN) as unique_companies
        FROM outreach_analytics WHERE Reply_Received = 1 {flt}
    """)
    reply_row = cursor.fetchone()
    reply_stats = dict(reply_row) if reply_row else {"total_replies": 0, "unique_companies": 0}

    cursor.execute(f"SELECT COUNT(*) FROM outreach_analytics WHERE 1=1 {flt}")
    total_sent = cursor.fetchone()[0]
    reply_stats["reply_rate"] = round(reply_stats["total_replies"] / total_sent * 100, 1) if total_sent > 0 else 0

    conn.close()

    return {
        "variants": variants,
        "deliverability": deliverability,
        "reply_stats": reply_stats,
    }