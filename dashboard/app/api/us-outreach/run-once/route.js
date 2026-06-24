// POST /api/us-outreach/run-once
// Hosted dashboard can't execute on the Mac, so enqueue an intent row in
// command_queue; command_worker.py (in tick.sh) runs orchestrator.run_cycle next tick.
import { run, json } from '../../../lib/turso.server'

export async function POST() {
  await run(
    `INSERT INTO command_queue (Action, Status, Requested_At)
     VALUES ('run_once', 'pending', strftime('%Y-%m-%d %H:%M:%S','now'))`,
  )
  return json({ ok: true, message: 'cycle queued — the Mac will run it on the next tick' })
}
