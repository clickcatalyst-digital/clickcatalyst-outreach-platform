# email_engine_04.py
# Input:  company_enrichment rows with Pipeline_Status = 'Intelligence_Ready'
# Action: Renders HTML email, embeds scatter plot inline, sends via Gmail SMTP
# Output: Updates outreach_analytics + sets Pipeline_Status = 'Outreach_Sent'
# Flow: for each lead, it checks NIC code → picks variant (ecomm/saas/agency/generic) → A/B splits → pulls the matching template from campaign_templates → renders with variables → sends → logs the variant used to outreach_analytics. Your analytics dashboard will then show click rates broken down by variant

import sqlite3
import pandas as pd
import smtplib
import ssl
import os
import time
import random
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import date
from dotenv import load_dotenv
from visualizer import generate_scatter_plot
from api.campaign_engine import get_campaign_variant, get_ab_variant

load_dotenv()

DB_PATH = '/Users/pujan/Developer/data_collector/indian_companies/company_master_data.db'

# --- Gmail SMTP config ---
SMTP_HOST     = 'smtp.gmail.com'
SMTP_PORT     = 465                          # SSL
SENDER_EMAIL  = os.getenv('SENDER_EMAIL')    # your Gmail address
SENDER_PASS   = os.getenv('SENDER_APP_PASS') # Gmail App Password (not your login password)
SENDER_NAME   = 'Pujan from ClickCatalyst'

# --- UTM / tracking config ---
AUDIT_BASE_URL  = 'https://clickcatalyst.digital/free-audit'
UTM_SOURCE      = 'coldemail'
UTM_MEDIUM      = 'outreach'

# --- Tracking config ---
TRACKING_BASE_URL = 'https://clickcatalyst.digital/api/track'
UNSUB_BASE_URL    = 'https://clickcatalyst.digital/api/unsubscribe'

# ---------------------------------------------------------------------------
# HTML EMAIL TEMPLATE
# ---------------------------------------------------------------------------

def render_email_html(company_name, personalized_sentence, audit_url, plot_cid, tracking_pixel_url='', unsubscribe_url=''):
    """
    Renders the hybrid HTML email body.
    Keeps HTML minimal — bold names, inline image, one hyperlink.
    plot_cid is the Content-ID used to reference the inline image.
    """
    return f"""
<!DOCTYPE html>
<html lang="en">
<body style="margin:0;padding:0;background:#ffffff;font-family:Georgia,serif;color:#1a1a2e;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table width="580" cellpadding="0" cellspacing="0" border="0"
               style="max-width:580px;width:100%;">

          <!-- Greeting -->
          <tr>
            <td style="padding-bottom:20px;font-size:15px;line-height:1.7;color:#1a1a2e;">
              Hi,
            </td>
          </tr>

          <!-- Opening hook -->
          <tr>
            <td style="padding-bottom:20px;font-size:15px;line-height:1.7;color:#1a1a2e;">
              I was reviewing Google Ads activity in your segment and came across
              <strong>{company_name}</strong>.
            </td>
          </tr>

          <!-- Personalized intelligence sentence -->
          <tr>
            <td style="padding-bottom:24px;font-size:15px;line-height:1.7;color:#1a1a2e;">
              {personalized_sentence}
            </td>
          </tr>

          <!-- Scatter plot inline -->
          <tr>
            <td style="padding-bottom:24px;text-align:center;">
              <img src="cid:{plot_cid}"
                   alt="Competitive Landscape — {company_name}"
                   width="560"
                   style="max-width:100%;border:1px solid #e0e0e0;border-radius:4px;" />
            </td>
          </tr>

          <!-- CTA sentence -->
          <tr>
            <td style="padding-bottom:20px;font-size:15px;line-height:1.7;color:#1a1a2e;">
              I ran a quick audit on <strong>{company_name}</strong>'s account structure and found
              a few specific inefficiencies worth flagging. You can
              <a href="{audit_url}"
                 style="color:#e63946;font-weight:bold;text-decoration:none;">
                view the full leak report here
              </a>.
            </td>
          </tr>

          <!-- Sign-off -->
          <tr>
            <td style="padding-bottom:8px;font-size:15px;line-height:1.7;color:#1a1a2e;">
              Happy to walk you through it if useful.
            </td>
          </tr>
          <tr>
            <td style="font-size:15px;line-height:1.7;color:#1a1a2e;">
              Pujan<br/>
              <span style="color:#6c757d;font-size:13px;">
                ClickCatalyst · clickcatalyst.digital
              </span>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding-top:32px;font-size:11px;color:#aaaaaa;border-top:1px solid #f0f0f0;">
              You're receiving this because your company appears in publicly available
              MCA registration data. To stop receiving these emails,
              <a href="{unsubscribe_url}" style="color:#aaaaaa;text-decoration:underline;">unsubscribe here</a>.
            </td>
          </tr>
          <!-- Open tracking pixel -->
          <tr>
            <td>
              <img src="{tracking_pixel_url}" width="1" height="1" alt="" style="display:block;" />
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def render_email_plaintext(company_name, personalized_sentence, audit_url, unsubscribe_url=''):
    """Plain text fallback for email clients that don't render HTML."""
    return f"""Hi,

I was reviewing Google Ads activity in your segment and came across {company_name}.

{personalized_sentence}

I ran a quick audit on {company_name}'s account structure and found a few specific inefficiencies worth flagging. You can view the full leak report here: {audit_url}

Happy to walk you through it if useful.

Pujan
ClickCatalyst · clickcatalyst.digital

---
You're receiving this because your company appears in publicly available MCA registration data.
To stop receiving these emails, visit: {unsubscribe_url}
"""


# ---------------------------------------------------------------------------
# UTM LINK BUILDER
# ---------------------------------------------------------------------------

def build_audit_url(cin, batch_id):
    return (
        f"{AUDIT_BASE_URL}"
        f"?utm_source={UTM_SOURCE}"
        f"&utm_medium={UTM_MEDIUM}"
        f"&utm_campaign={batch_id}"
        f"&cin={cin}"
    )


# ---------------------------------------------------------------------------
# SMTP SEND
# ---------------------------------------------------------------------------

def send_email(to_address, subject, html_body, plain_body, plot_buffer, plot_cid):
    """
    Sends HTML email with inline scatter plot via Gmail SMTP SSL.
    plot_buffer: BytesIO from visualizer.generate_scatter_plot()
    plot_cid:    Content-ID string (without angle brackets)
    """
    msg = MIMEMultipart('related')
    msg['Subject'] = subject
    msg['From']    = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    msg['To']      = to_address

    # Attach HTML + plain text as alternatives
    alt = MIMEMultipart('alternative')
    alt.attach(MIMEText(plain_body, 'plain', 'utf-8'))
    alt.attach(MIMEText(html_body,  'html',  'utf-8'))
    msg.attach(alt)

    # Attach inline plot image
    if plot_buffer:
        img = MIMEImage(plot_buffer.read(), _subtype='png')
        img.add_header('Content-ID', f'<{plot_cid}>')
        img.add_header('Content-Disposition', 'inline', filename=f'{plot_cid}.png')
        msg.attach(img)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
        server.login(SENDER_EMAIL, SENDER_PASS)
        server.sendmail(SENDER_EMAIL, to_address, msg.as_string())


# ---------------------------------------------------------------------------
# ANALYTICS LOGGER
# ---------------------------------------------------------------------------

def log_to_outreach_analytics(cursor, cin, batch_id, utm_campaign, variant_key=None, subject_line=None):
    """Inserts a send record into outreach_analytics."""
    cursor.execute("""
        INSERT INTO outreach_analytics
            (CIN, Email_Sent_Date, Batch_ID, UTM_Campaign, Campaign_Variant, Subject_Line)
        VALUES (?, CURRENT_DATE, ?, ?, ?, ?)
    """, (cin, batch_id, utm_campaign, variant_key, subject_line))


def mark_pipeline_sent(cursor, cin):
    """Updates company_enrichment to reflect email was sent."""
    cursor.execute("""
        UPDATE company_enrichment
        SET Email_Sent_Date  = CURRENT_DATE,
            Pipeline_Status  = 'Outreach_Sent'
        WHERE CIN = ?
    """, (cin,))


# ---------------------------------------------------------------------------
# BATCH RUNNER
# ---------------------------------------------------------------------------

def run_email_batch(recipient_email_override=None, batch_size=50, db_path=DB_PATH):
    """
    Pulls Intelligence_Ready leads, renders + sends one email per lead.
    
    recipient_email_override: if set, sends ALL emails to this address instead
                              of the real lead email. Use for testing.
    """
    print("📧 INITIALIZING EMAIL ENGINE 📧\n")

    batch_id = f"batch_{date.today().isoformat().replace('-', '_')}"

    conn   = sqlite3.connect(db_path)
    cursor = conn.cursor()

    df_targets = pd.read_sql_query("""
        SELECT
            q.CIN,
            q.CompanyName,
            e.Personalized_Sentence,
            e.Website_URL
        FROM vw_qualified_leads q
        JOIN company_enrichment e ON q.CIN = e.CIN
        WHERE e.Pipeline_Status = 'Intelligence_Ready'
        AND (e.Unsubscribed IS NULL OR e.Unsubscribed = 0)
        LIMIT ?;
    """, conn, params=(batch_size,))

    if df_targets.empty:
        print("No leads ready for outreach. Run intelligence_engine.py first.")
        conn.close()
        return

    print(f"Loaded {len(df_targets)} leads for batch: {batch_id}\n")

    sent_count   = 0
    failed_count = 0

    for _, row in df_targets.iterrows():
        cin          = row['CIN']
        company_name = row['CompanyName'].title()
        sentence     = row['Personalized_Sentence']
        print("=" * 60)
        print(f"Processing: {company_name} ({cin})")

        # --- Build UTM audit link ---
        audit_url = build_audit_url(cin, batch_id)

        # --- Build tracking URLs ---
        analytics_id_row = cursor.execute("SELECT MAX(Analytics_ID) + 1 FROM outreach_analytics").fetchone()
        next_analytics_id = analytics_id_row[0] if analytics_id_row[0] else 1
        tracking_pixel_url = f"{TRACKING_BASE_URL}/email-open?aid={next_analytics_id}"
        audit_url = f"{TRACKING_BASE_URL}/email-click?aid={next_analytics_id}&cin={cin}&url={audit_url}"
        unsubscribe_url = f"{UNSUB_BASE_URL}?cin={cin}"

        # --- Generate scatter plot ---
        plot_cid = f"scatter_{cin}"
        _, plot_buffer = generate_scatter_plot(cin, company_name, db_path)

        if plot_buffer is None:
            print(f"   [Email] No plot generated — skipping {cin}")
            failed_count += 1
            continue

        # --- Pick campaign variant ---
        lead_info = cursor.execute("""
            SELECT q.nic_code, e.Competitor_Count, e.Has_GMB
            FROM vw_qualified_leads q
            JOIN company_enrichment e ON q.CIN = e.CIN
            WHERE q.CIN = ?
        """, (cin,)).fetchone()

        # Thompson Sampling
        if lead_info:
            variant_base = get_campaign_variant(dict(lead_info))
            try:
                from bayesian_engine import select_variant_thompson
                variant_key = select_variant_thompson(variant_base, cin)
            except ImportError:
                variant_key = get_ab_variant(cin, variant_base)
        else:
            variant_key = 'generic_audit_v1_a'

        # --- Fetch template from DB ---
        tmpl = cursor.execute(
            "SELECT * FROM campaign_templates WHERE Variant_Key = ? AND Is_Active = 1",
            (variant_key,)
        ).fetchone()

        if tmpl:
            tmpl = dict(tmpl)
            sample = {
                'company_name': company_name,
                'personalized_sentence': sentence,
                'audit_url': audit_url,
                'competitor_count': str(lead_info['Competitor_Count'] or 0) if lead_info else '0',
                'tracking_pixel_url': tracking_pixel_url,
                'unsubscribe_url': unsubscribe_url,
            }
            html_body = tmpl['Body_HTML']
            plain_body = tmpl['Body_Plain']
            subject = tmpl['Subject_Line']
            for k, v in sample.items():
                html_body  = html_body.replace('{' + k + '}', v)
                plain_body = plain_body.replace('{' + k + '}', v)
                subject    = subject.replace('{' + k + '}', v)
        else:
            # Fallback to hardcoded template if variant not found in DB
            html_body  = render_email_html(company_name, sentence, audit_url, plot_cid, tracking_pixel_url, unsubscribe_url)
            plain_body = render_email_plaintext(company_name, sentence, audit_url, unsubscribe_url)
            subject    = f"Google Ads audit — {company_name}"

        # --- Determine recipient ---
        # NOTE: real lead email lookup goes here once you have an email column.
        # For now we use override (test mode) or skip if no email available.
        to_address = recipient_email_override
        if not to_address:
            contact_row = cursor.execute("""
                SELECT Email_Address FROM company_contacts
                WHERE CIN = ? AND Is_Primary_Contact = 1
                LIMIT 1
            """, (cin,)).fetchone()
            if contact_row:
                to_address = contact_row[0]

        if not to_address:
            print(f"   [Email] No recipient address available for {cin} — skipping.")
            failed_count += 1
            continue

        # --- Send ---
        try:
            send_email(to_address, subject, html_body, plain_body, plot_buffer, plot_cid)
            print(f"   ✅ Sent to {to_address}")

            # Log success
            log_to_outreach_analytics(cursor, cin, batch_id, batch_id, variant_key, subject)
            mark_pipeline_sent(cursor, cin)
            conn.commit()
            sent_count += 1

        except Exception as e:
            error_msg = str(e).lower()
            print(f"   ❌ Send failed for {cin}: {e}")
            failed_count += 1

            # Classify bounce type
            hard_bounce_signals = [
                'user unknown', 'mailbox not found', 'recipient rejected',
                'address rejected', 'no such user', 'does not exist',
                'invalid recipient', 'account disabled', 'mailbox unavailable',
                '550', '551', '552', '553', '554'
            ]
            is_hard_bounce = any(signal in error_msg for signal in hard_bounce_signals)

            if is_hard_bounce:
                print(f"   ⛔ HARD BOUNCE — marking contact as invalid")
                cursor.execute("""
                    UPDATE outreach_analytics
                    SET Bounced = 1, Send_Error = ?
                    WHERE CIN = ? AND Email_Sent_Date = date('now')
                """, (str(e)[:200], cin))
                # Mark the contact email as bad so we never retry
                cursor.execute("""
                    UPDATE company_contacts
                    SET Email_Label = 'Bounced'
                    WHERE CIN = ? AND Is_Primary_Contact = 1
                """, (cin,))
                cursor.execute("""
                    UPDATE company_enrichment
                    SET Pipeline_Status = 'Hard_Bounce', Last_Error = ?
                    WHERE CIN = ?
                """, (f"Hard bounce: {str(e)[:150]}", cin))
            else:
                print(f"   ⚠ SOFT BOUNCE — will retry next run")
                cursor.execute("""
                    UPDATE company_enrichment
                    SET Last_Error = ?
                    WHERE CIN = ?
                """, (f"Soft bounce: {str(e)[:150]}", cin))

            conn.commit()

        # --- Human-like delay ---
        delay = random.randint(30, 90)
        print(f"   Waiting {delay}s before next send...")
        time.sleep(delay)

    conn.close()
    print("=" * 60)
    print(f"🏁 EMAIL BATCH COMPLETE — {batch_id}")
    print(f"   ✅ Sent:   {sent_count}")
    print(f"   ❌ Failed: {failed_count}")


# --- Execute ---
# For testing: sends all to your own inbox
# run_email_batch(recipient_email_override='you@gmail.com')

# For production: remove override once email column exists in enrichment table
# run_email_batch()