// GET /api/system-health — one Turso-backed aggregate of the whole pipeline's health
// plus the lead funnel. Powers the System Health page, the US Outreach funnel band,
// and the `doctor` CLI. Pure reads; US-scoped.
import { q, q1, scalar, json } from '../../lib/turso.server'

export const dynamic = 'force-dynamic'

const AGE = (col) => `(julianday('now') - julianday(${col})) * 1440` // minutes, UTC-based

export async function GET() {
  try {
    const [
      cfgRows, macAge, syncAge, cycleAge, bayes, queuePending, lastSend,
      alerts, templatesActive, testEmails,
      generated, qualified, ready, sent, opened, clicked, replied,
      sentToday, testSent, lastTest,
    ] = await Promise.all([
      q('SELECT Config_Key, Config_Value FROM us_scheduler_config'),
      scalar(`SELECT ${AGE('Last_Beat_At')} FROM mac_heartbeat WHERE ID=1`),
      scalar(`SELECT ${AGE('Last_Sync_At')} FROM tracking_sync_heartbeat WHERE ID=1`),
      scalar(`SELECT ${AGE('Config_Value')} FROM us_scheduler_config WHERE Config_Key='last_cycle_at'`),
      q1(`SELECT Updated_At, ${AGE('Updated_At')} AS age FROM bayesian_state WHERE ID=1`),
      scalar(`SELECT COUNT(*) FROM command_queue WHERE Status='pending'`, [], 0),
      scalar(`SELECT MAX(Email_Sent_Date) FROM company_enrichment WHERE Lead_Source='US_Apollo'`),
      q(`SELECT Level, Code, Message FROM us_alerts WHERE Active=1
         ORDER BY CASE Level WHEN 'red' THEN 0 WHEN 'yellow' THEN 1 ELSE 2 END`),
      scalar(`SELECT COUNT(*) FROM campaign_templates WHERE Is_Active=1 AND Variant_Key LIKE 'us\\_%' ESCAPE '\\'`, [], 0),
      scalar(`SELECT COUNT(*) FROM us_test_emails`, [], 0),
      // funnel
      scalar(`SELECT COUNT(*) FROM company_enrichment WHERE Lead_Source='US_Apollo'`, [], 0),
      scalar(`SELECT COUNT(DISTINCT e.CIN) FROM company_enrichment e
              JOIN company_contacts cc ON e.CIN=cc.CIN AND cc.Is_Primary_Contact=1
              WHERE e.Lead_Source='US_Apollo' AND (cc.Email_Label IS NULL OR cc.Email_Label!='Bounced')`, [], 0),
      scalar(`SELECT COUNT(*) FROM company_enrichment WHERE Lead_Source='US_Apollo' AND Pipeline_Status='Intelligence_Ready'`, [], 0),
      scalar(`SELECT COUNT(*) FROM company_enrichment WHERE Lead_Source='US_Apollo' AND Email_Sent_Date IS NOT NULL`, [], 0),
      scalar(`SELECT COUNT(DISTINCT CIN) FROM outreach_analytics WHERE CIN LIKE 'APOLLO_%' AND Email_Opened=1 AND Batch_ID NOT LIKE 'ustest%'`, [], 0),
      scalar(`SELECT COUNT(DISTINCT CIN) FROM outreach_analytics WHERE CIN LIKE 'APOLLO_%' AND Audit_Link_Clicked=1 AND Batch_ID NOT LIKE 'ustest%'`, [], 0),
      scalar(`SELECT COUNT(DISTINCT CIN) FROM outreach_analytics WHERE CIN LIKE 'APOLLO_%' AND Reply_Received=1 AND Batch_ID NOT LIKE 'ustest%'`, [], 0),
      scalar(`SELECT COUNT(*) FROM outreach_analytics WHERE CIN LIKE 'APOLLO_%' AND Email_Sent_Date=date('now') AND Batch_ID NOT LIKE 'ustest%'`, [], 0),
      scalar(`SELECT COUNT(*) FROM outreach_analytics WHERE Batch_ID LIKE 'ustest%'`, [], 0),
      scalar(`SELECT MAX(Email_Sent_Date) FROM outreach_analytics WHERE Batch_ID LIKE 'ustest%'`),
    ])

    const cfg = {}
    for (const r of cfgRows) cfg[r.Config_Key] = r.Config_Value

    const num = (v) => (v == null ? null : Number(v))
    const macA = num(macAge), syncA = num(syncAge), cycleA = num(cycleAge)
    const bayesA = bayes ? num(bayes.age) : null
    const cycleThreshold = Math.max(25, parseInt(cfg.cycle_minutes || '20', 10) + 5)
    const enabled = cfg.enabled === 'true'
    const mode = cfg.mode || 'test'
    const redAlerts = alerts.filter((a) => a.Level === 'red').length

    const gen = num(generated), qual = num(qualified), rdy = num(ready), snt = num(sent)
    const funnel = {
      generated: gen, qualified: qual, ready: rdy, sent: snt,
      opened: num(opened), clicked: num(clicked), replied: num(replied),
      never_emailed: Math.max(0, gen - snt),
    }

    const signals = {
      database: { ok: true, value: 'connected' },
      mac: { ok: macA != null && macA < 3, age_min: macA, value: macA == null ? 'no beat' : (macA < 3 ? 'online' : 'offline') },
      scheduler: { ok: enabled, value: enabled ? 'running' : 'paused', mode },
      orchestrator: { ok: cycleA != null && cycleA < cycleThreshold, age_min: cycleA, last_cycle_at: cfg.last_cycle_at || null },
      tracking_sync: { ok: syncA != null && syncA < 25, age_min: syncA },
      command_queue: { ok: Number(queuePending) === 0, pending: Number(queuePending) },
      last_send: { value: lastSend || null, today: Number(sentToday) },
      bayesian: { ok: bayesA != null && bayesA < 1440, age_min: bayesA, updated_at: bayes ? bayes.Updated_At : null },
      alerts: { ok: redAlerts === 0, count: alerts.length, red: redAlerts, items: alerts },
      campaign_templates: { ok: Number(templatesActive) > 0, active: Number(templatesActive) },
      test_recipients: { ok: !(mode === 'test') || Number(testEmails) > 0, count: Number(testEmails) },
    }

    const allOk = Object.values(signals).every((s) => s.ok !== false)

    return json({
      ok: allOk,
      mode,
      funnel,
      signals,
      testing: { sent: Number(testSent), last_test_at: lastTest || null },
    })
  } catch (e) {
    return json({ ok: false, error: String(e?.message || e),
      signals: { database: { ok: false, value: 'unreachable' } } }, { status: 503 })
  }
}
