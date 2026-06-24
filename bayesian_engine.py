#!/usr/bin/env python3
"""
bayesian_engine.py

Two models for the outreach pipeline:

1. Thompson Sampling for Variant Selection
   - Maintains Beta priors per variant
   - Updates from observed conversions (or clicks/replies as proxy)
   - Selects variants probabilistically (explore/exploit)

2. Bayesian Deliverability Estimator
   - Hidden state: domain reputation (0-1)
   - Observables: open rate, reply rate, bounce rate, volume
   - Updates reputation estimate after each batch
   - Provides send/don't-send signal

Usage:
    # As a library — called by email_engine_04.py
    from bayesian_engine import select_variant_thompson, update_posteriors, get_deliverability_score

    # Standalone — show current model state
    python bayesian_engine.py                    # show all posteriors + deliverability
    python bayesian_engine.py --recommend 10     # recommend next 10 variant assignments
    python bayesian_engine.py --update           # update posteriors from latest data
    python bayesian_engine.py --deliverability   # show deliverability analysis

Integration with email_engine_04.py:
    Replace the deterministic A/B split with Thompson Sampling by calling
    select_variant_thompson() instead of get_ab_variant().
    The engine falls back to uniform random if insufficient data.
"""

import sqlite3
import os
import sys
import json
import math
import random
import argparse
from datetime import datetime, timedelta, date
from collections import defaultdict

DB_PATH = os.getenv(
    'DB_PATH',
    '/Users/pujan/Developer/data_collector/indian_companies/company_master_data.db'
)

# File to persist model state between runs
MODEL_STATE_FILE = os.getenv('MODEL_STATE', 'bayesian_model_state.json')


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1: THOMPSON SAMPLING FOR VARIANT SELECTION
# ═══════════════════════════════════════════════════════════════════════════════

class ThompsonSampler:
    """
    Maintains Beta(alpha, beta) posteriors for each variant.

    alpha = successes + prior
    beta  = failures + prior

    The "success" metric is configurable:
      - 'click'      → Audit_Link_Clicked = 1
      - 'reply'      → Reply_Received = 1
      - 'conversion'  → Converted = 1

    With weak priors (alpha=1, beta=1 = uniform), the model
    explores aggressively early and exploits as data accumulates.
    """

    def __init__(self, success_metric='click', prior_alpha=1, prior_beta=1):
        self.success_metric = success_metric
        self.prior_alpha = prior_alpha
        self.prior_beta = prior_beta
        self.posteriors = {}  # variant_key → {'alpha': float, 'beta': float}

    def load_from_db(self):
        """Compute posteriors from outreach_analytics data."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        metric_col = {
            'click': 'Audit_Link_Clicked',
            'reply': 'Reply_Received',
            'conversion': 'Converted',
        }[self.success_metric]

        cursor.execute(f"""
            SELECT
                Campaign_Variant,
                COUNT(*) as total,
                SUM(CASE WHEN {metric_col} = 1 THEN 1 ELSE 0 END) as successes
            FROM outreach_analytics
            WHERE Campaign_Variant IS NOT NULL
            GROUP BY Campaign_Variant
        """)

        self.posteriors = {}
        for row in cursor.fetchall():
            variant, total, successes = row
            failures = total - successes
            self.posteriors[variant] = {
                'alpha': self.prior_alpha + successes,
                'beta': self.prior_beta + failures,
                'total': total,
                'successes': successes,
            }

        conn.close()

    def sample(self, variant_key):
        """Draw a sample from the Beta posterior for a variant."""
        if variant_key not in self.posteriors:
            # No data — use prior (uniform)
            return random.betavariate(self.prior_alpha, self.prior_beta)

        p = self.posteriors[variant_key]
        return random.betavariate(p['alpha'], p['beta'])

    def select_variant(self, variant_base, cin=None):
        """
        Given a variant base (e.g. 'ecomm_pmax_v1'), select _a or _b
        using Thompson Sampling.

        Falls back to deterministic A/B split if no data exists.
        """
        variant_a = f"{variant_base}_a"
        variant_b = f"{variant_base}_b"

        # If neither variant has data, fall back to deterministic split
        has_data = variant_a in self.posteriors or variant_b in self.posteriors
        if not has_data:
            if cin:
                bucket = sum(ord(c) for c in cin) % 2
                return variant_a if bucket == 0 else variant_b
            return random.choice([variant_a, variant_b])

        # Thompson Sampling: draw from each posterior, pick the higher sample
        sample_a = self.sample(variant_a)
        sample_b = self.sample(variant_b)

        return variant_a if sample_a >= sample_b else variant_b

    def get_summary(self):
        """Return human-readable summary of all posteriors."""
        summary = []
        for variant, p in sorted(self.posteriors.items()):
            mean = p['alpha'] / (p['alpha'] + p['beta'])
            # 95% credible interval (Beta quantiles approximation)
            lo = max(0, mean - 1.96 * math.sqrt(mean * (1 - mean) / max(p['total'], 1)))
            hi = min(1, mean + 1.96 * math.sqrt(mean * (1 - mean) / max(p['total'], 1)))
            summary.append({
                'variant': variant,
                'total': p['total'],
                'successes': p['successes'],
                'mean': round(mean, 4),
                'ci_low': round(lo, 4),
                'ci_high': round(hi, 4),
                'alpha': p['alpha'],
                'beta': p['beta'],
            })
        return summary


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2: BAYESIAN DELIVERABILITY ESTIMATOR
# ═══════════════════════════════════════════════════════════════════════════════

class DeliverabilityEstimator:
    """
    Estimates domain reputation as a hidden state.

    State: reputation ∈ [0, 1]
    Observations: open_rate, reply_rate, bounce_rate, volume

    Uses a simple Bayesian update:
        reputation_new = w * reputation_old + (1-w) * observed_signal

    Where observed_signal is a weighted combination of metrics,
    and w is a decay factor that controls how much history matters.

    This is intentionally simple — a Kalman filter or HMM would be
    more principled but overkill for < 1000 data points.
    """

    def __init__(self):
        self.reputation = 0.7  # Optimistic prior for a new domain
        self.history = []
        self.decay = 0.8       # How much to weight history vs new data

    def load_state(self):
        """Load persisted state from disk."""
        if os.path.exists(MODEL_STATE_FILE):
            with open(MODEL_STATE_FILE, 'r') as f:
                state = json.load(f)
                self.reputation = state.get('reputation', 0.7)
                self.history = state.get('history', [])
                self.decay = state.get('decay', 0.8)

    def save_state(self):
        """Persist state to disk."""
        with open(MODEL_STATE_FILE, 'w') as f:
            json.dump({
                'reputation': self.reputation,
                'history': self.history[-90:],  # Keep last 90 entries
                'decay': self.decay,
                'updated_at': datetime.now().isoformat(),
            }, f, indent=2)

    def compute_daily_signals(self):
        """Pull daily aggregate signals from outreach_analytics."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                Email_Sent_Date,
                COUNT(*) as sent,
                SUM(CASE WHEN Email_Opened = 1 THEN 1 ELSE 0 END) as opened,
                SUM(CASE WHEN Audit_Link_Clicked = 1 THEN 1 ELSE 0 END) as clicked,
                SUM(CASE WHEN Reply_Received = 1 THEN 1 ELSE 0 END) as replied,
                SUM(CASE WHEN Bounced = 1 THEN 1 ELSE 0 END) as bounced,
                SUM(CASE WHEN Converted = 1 THEN 1 ELSE 0 END) as converted
            FROM outreach_analytics
            WHERE Email_Sent_Date >= date('now', '-30 days')
            GROUP BY Email_Sent_Date
            ORDER BY Email_Sent_Date ASC
        """)

        days = []
        for row in cursor.fetchall():
            d = {
                'date': row[0],
                'sent': row[1],
                'opened': row[2],
                'clicked': row[3],
                'replied': row[4],
                'bounced': row[5],
                'converted': row[6],
            }
            d['open_rate'] = d['opened'] / d['sent'] if d['sent'] > 0 else 0
            d['click_rate'] = d['clicked'] / d['sent'] if d['sent'] > 0 else 0
            d['reply_rate'] = d['replied'] / d['sent'] if d['sent'] > 0 else 0
            d['bounce_rate'] = d['bounced'] / d['sent'] if d['sent'] > 0 else 0
            d['conversion_rate'] = d['converted'] / d['sent'] if d['sent'] > 0 else 0
            days.append(d)

        # Get daily unsubscribe count
        cursor.execute("""
            SELECT Unsubscribed_Date, COUNT(*) as count
            FROM company_enrichment
            WHERE Unsubscribed = 1 AND Unsubscribed_Date >= date('now', '-30 days')
            GROUP BY Unsubscribed_Date
        """)
        unsub_by_date = {row[0]: row[1] for row in cursor.fetchall()}

        for d in days:
            d['unsubscribed'] = unsub_by_date.get(d['date'], 0)

        conn.close()
        return days

    def update(self):
        """Update reputation estimate from latest data."""
        days = self.compute_daily_signals()

        if not days:
            return

        for day in days:
            # Already processed?
            if any(h.get('date') == day['date'] for h in self.history):
                continue

            # Composite signal: weighted combination of observable metrics
            # Open rate is strongest signal, bounce rate is strongly negative
            # Volume penalty: sending more than warmup limit degrades signal
            volume_penalty = 0.0
            if day['sent'] > 50:
                volume_penalty = min(0.15, (day['sent'] - 50) / 500)

            # Unsubscribe signal (strong negative)
            unsub_rate = day.get('unsubscribed', 0) / day['sent'] if day['sent'] > 0 else 0

            signal = (
                0.10 * day['open_rate'] +
                0.35 * day['reply_rate'] +
                0.15 * day['click_rate'] +
                0.15 * (1.0 - day['bounce_rate']) +
                0.10 * (1.0 - unsub_rate) +
                0.15 * day.get('conversion_rate', 0)
            ) - volume_penalty
            signal = max(0.0, min(1.0, signal))

            # Bayesian update: blend prior with new observation
            self.reputation = self.decay * self.reputation + (1 - self.decay) * signal

            # Clamp to [0.05, 0.99]
            self.reputation = max(0.05, min(0.99, self.reputation))

            self.history.append({
                'date': day['date'],
                'signal': round(signal, 4),
                'reputation': round(self.reputation, 4),
                'sent': day['sent'],
                'open_rate': round(day['open_rate'], 4),
                'reply_rate': round(day['reply_rate'], 4),
                'bounce_rate': round(day['bounce_rate'], 4),
            })

        self.save_state()

    def get_send_recommendation(self):
        """Should we send today? Returns (should_send, reason, confidence)."""
        if self.reputation >= 0.6:
            return True, "Reputation healthy", self.reputation
        elif self.reputation >= 0.4:
            return True, "Reputation moderate — consider reducing volume", self.reputation
        elif self.reputation >= 0.2:
            return False, "Reputation degraded — pause and investigate", self.reputation
        else:
            return False, "Reputation critical — stop all sends", self.reputation

    def get_volume_multiplier(self):
        """How much to scale today's volume based on reputation."""
        if self.reputation >= 0.7:
            return 1.0    # Full volume
        elif self.reputation >= 0.5:
            return 0.7    # Reduce 30%
        elif self.reputation >= 0.3:
            return 0.4    # Reduce 60%
        else:
            return 0.0    # Stop

    def get_summary(self):
        """Human-readable deliverability summary."""
        should_send, reason, confidence = self.get_send_recommendation()
        multiplier = self.get_volume_multiplier()

        return {
            'reputation': round(self.reputation, 4),
            'should_send': should_send,
            'reason': reason,
            'volume_multiplier': multiplier,
            'history_days': len(self.history),
            'last_updated': self.history[-1]['date'] if self.history else None,
            'trend': self._compute_trend(),
        }

    def _compute_trend(self):
        """Is reputation improving or declining?"""
        if len(self.history) < 3:
            return 'insufficient_data'

        recent = [h['reputation'] for h in self.history[-5:]]
        older = [h['reputation'] for h in self.history[-10:-5]] if len(self.history) >= 10 else [h['reputation'] for h in self.history[:5]]

        avg_recent = sum(recent) / len(recent)
        avg_older = sum(older) / len(older) if older else avg_recent

        diff = avg_recent - avg_older
        if diff > 0.05:
            return 'improving'
        elif diff < -0.05:
            return 'declining'
        return 'stable'


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API — for use by email_engine_04.py
# ═══════════════════════════════════════════════════════════════════════════════

_sampler = None
_estimator = None


def get_sampler(metric='click'):
    """Get or create the Thompson Sampler singleton."""
    global _sampler
    if _sampler is None or _sampler.success_metric != metric:
        _sampler = ThompsonSampler(success_metric=metric)
        _sampler.load_from_db()
    return _sampler


def get_estimator():
    """Get or create the Deliverability Estimator singleton."""
    global _estimator
    if _estimator is None:
        _estimator = DeliverabilityEstimator()
        _estimator.load_state()
    return _estimator


def select_variant_thompson(variant_base, cin=None, metric='click'):
    """
    Drop-in replacement for get_ab_variant() in campaign_engine.py.
    Uses Thompson Sampling when data exists, falls back to deterministic split.

    Usage in email_engine_04.py:
        # Replace:
        # variant_key = get_ab_variant(cin, variant_base)
        # With:
        from bayesian_engine import select_variant_thompson
        variant_key = select_variant_thompson(variant_base, cin)
    """
    sampler = get_sampler(metric)
    return sampler.select_variant(variant_base, cin)


def should_send_today():
    """
    Check if deliverability is healthy enough to send.

    Usage in send_scheduler.py or email_engine_04.py:
        from bayesian_engine import should_send_today
        ok, reason, score = should_send_today()
        if not ok:
            print(f"Skipping sends: {reason} (score: {score})")
    """
    estimator = get_estimator()
    estimator.update()
    return estimator.get_send_recommendation()


def get_volume_adjustment():
    """
    Get volume multiplier based on deliverability.

    Usage in send_scheduler.py:
        from bayesian_engine import get_volume_adjustment
        base_limit = get_daily_limit()
        adjusted = int(base_limit * get_volume_adjustment())
    """
    estimator = get_estimator()
    estimator.update()
    return estimator.get_volume_multiplier()


# ═══════════════════════════════════════════════════════════════════════════════
# CLI — standalone display + management
# ═══════════════════════════════════════════════════════════════════════════════

def display_posteriors(metric='click'):
    """Show Thompson Sampling posteriors for all variants."""
    sampler = ThompsonSampler(success_metric=metric)
    sampler.load_from_db()
    summary = sampler.get_summary()

    if not summary:
        print("   No variant data yet — send some emails first.")
        return

    print(f"   Metric: {metric}")
    print(f"   {'Variant':<38} {'Sent':>5} {'Succ':>5} {'Mean':>7} {'95% CI':>15}")
    print(f"   {'─'*38} {'─'*5} {'─'*5} {'─'*7} {'─'*15}")

    for s in summary:
        ci = f"[{s['ci_low']:.3f}, {s['ci_high']:.3f}]"
        print(f"   {s['variant']:<38} {s['total']:>5} {s['successes']:>5} {s['mean']:>7.4f} {ci:>15}")


def display_deliverability():
    """Show deliverability analysis."""
    estimator = DeliverabilityEstimator()
    estimator.load_state()
    estimator.update()
    s = estimator.get_summary()

    print(f"   Reputation:    {s['reputation']:.4f}")
    print(f"   Trend:         {s['trend']}")
    print(f"   Should send:   {'✅ Yes' if s['should_send'] else '❌ No'} — {s['reason']}")
    print(f"   Vol. multiplier: {s['volume_multiplier']:.1f}x")
    print(f"   History days:  {s['history_days']}")
    print(f"   Last updated:  {s['last_updated'] or 'never'}")

    if estimator.history:
        print()
        print(f"   📈 Reputation History (last 14 days):")
        for h in estimator.history[-14:]:
            bar = '█' * int(h['reputation'] * 20)
            print(f"      {h['date']}  {h['reputation']:.3f}  {bar}  sent={h['sent']}")


def display_recommendations(count=10, metric='click'):
    """Show recommended variant assignments for next N leads."""
    sampler = ThompsonSampler(success_metric=metric)
    sampler.load_from_db()

    # Get leads that need variants
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT q.CIN, q.CompanyName, q.nic_code, e.Competitor_Count, e.Has_GMB
        FROM vw_qualified_leads q
        JOIN company_enrichment e ON q.CIN = e.CIN
        JOIN company_contacts cc ON q.CIN = cc.CIN AND cc.Is_Primary_Contact = 1
        WHERE e.Pipeline_Status = 'Intelligence_Ready'
          AND (e.Unsubscribed IS NULL OR e.Unsubscribed = 0)
        LIMIT ?
    """, (count,))

    leads = cursor.fetchall()
    conn.close()

    if not leads:
        print("   No leads ready for variant assignment.")
        return

    # Import campaign engine for variant base selection
    try:
        from campaign_engine import get_campaign_variant
    except ImportError:
        try:
            from api.campaign_engine import get_campaign_variant
        except ImportError:
            print("   ⚠ Could not import campaign_engine — showing random assignments")
            get_campaign_variant = lambda _: 'generic_audit_v1'

    print(f"   Next {len(leads)} variant assignments (Thompson Sampling on '{metric}'):")
    print(f"   {'CIN':<22} {'Company':<25} {'Base Variant':<28} {'Selected'}")
    print(f"   {'─'*22} {'─'*25} {'─'*28} {'─'*35}")

    for cin, name, nic, comp_count, has_gmb in leads:
        lead_info = {'nic_code': nic, 'Competitor_Count': comp_count, 'Has_GMB': has_gmb}
        base = get_campaign_variant(lead_info)
        selected = sampler.select_variant(base, cin)
        print(f"   {cin:<22} {name[:23]:<25} {base:<28} {selected}")


def main():
    parser = argparse.ArgumentParser(description='Bayesian engine for outreach optimization')
    parser.add_argument('--update', action='store_true', help='Update posteriors from latest data')
    parser.add_argument('--recommend', type=int, metavar='N', help='Show N recommended variant assignments')
    parser.add_argument('--deliverability', action='store_true', help='Show deliverability analysis')
    parser.add_argument('--metric', default='click', choices=['click', 'reply', 'conversion'],
                        help='Success metric for Thompson Sampling (default: click)')
    args = parser.parse_args()

    print("🧠 BAYESIAN ENGINE")
    print(f"   DB: {DB_PATH}")
    print()

    if args.deliverability:
        print("── Deliverability Estimator ──")
        display_deliverability()
    elif args.recommend:
        display_recommendations(args.recommend, args.metric)
    elif args.update:
        print("── Updating Posteriors ──")
        sampler = ThompsonSampler(success_metric=args.metric)
        sampler.load_from_db()
        print(f"   Loaded {len(sampler.posteriors)} variants")

        print("\n── Updating Deliverability ──")
        estimator = DeliverabilityEstimator()
        estimator.load_state()
        estimator.update()
        print(f"   Reputation: {estimator.reputation:.4f}")
        print("   ✅ State saved.")
    else:
        print("── Thompson Sampling Posteriors ──")
        display_posteriors(args.metric)
        print()
        print("── Deliverability Estimator ──")
        display_deliverability()


if __name__ == '__main__':
    main()