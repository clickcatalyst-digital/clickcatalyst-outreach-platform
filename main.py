# main.py
# Master Orchestrator for the ClickCatalyst Outreach Pipeline
#
# Stages:
#   1. Domain Finder     → domain_extractor_01.py   → finds website for each lead
#   2. Pixel Checker     → pixel_checker_02.py       → confirms Google Ads pixel
#   3. Intelligence      → competition_intel_03.py → competitor analysis + email copy
#   4. Email Dispatch    → email_engine_04.py         → renders + sends emails
#
# Usage:
#   python main.py

import sys
import os

# ---------------------------------------------------------------------------
# SAFE IMPORTS — fail loudly if a module is missing
# ---------------------------------------------------------------------------

try:
    from domain_extractor_01   import run_enrichment_batch
    from pixel_checker_02      import run_pixel_batch
    from competition_intel_03 import run_intelligence_batch
    from email_engine_04       import run_email_batch
except ImportError as e:
    print(f"\n❌ Import Error: {e}")
    print("Make sure all pipeline scripts are in the same directory as main.py.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# PROMPT HELPERS
# ---------------------------------------------------------------------------

def prompt_int(message, default):
    """Prompts for an integer, falls back to default on empty input."""
    try:
        val = input(f"{message} [default: {default}]: ").strip()
        return int(val) if val else default
    except ValueError:
        print(f"   Invalid input — using default: {default}")
        return default


def prompt_yes_no(message, default=True):
    """Prompts for y/n, returns bool."""
    default_str = 'Y/n' if default else 'y/N'
    val = input(f"{message} [{default_str}]: ").strip().lower()
    if val == '':
        return default
    return val in ('y', 'yes')


def prompt_choice(message, options):
    """
    Displays a numbered menu and returns the chosen index (0-based).
    options: list of strings
    """
    print(f"\n{message}")
    for i, opt in enumerate(options, 1):
        print(f"  [{i}] {opt}")
    while True:
        try:
            val = input("Enter choice: ").strip()
            idx = int(val) - 1
            if 0 <= idx < len(options):
                return idx
            print(f"   Please enter a number between 1 and {len(options)}.")
        except ValueError:
            print("   Invalid input. Please enter a number.")


def divider(title=''):
    width = 60
    if title:
        pad = (width - len(title) - 2) // 2
        print("\n" + "─" * pad + f" {title} " + "─" * pad)
    else:
        print("\n" + "─" * width)


# ---------------------------------------------------------------------------
# INTERACTIVE CONFIG COLLECTION
# ---------------------------------------------------------------------------

def collect_config():
    """
    Walks the user through all pipeline options interactively.
    Returns a config dict.
    """
    print("\n" + "═" * 60)
    print("  ClickCatalyst Outreach Pipeline — Master Orchestrator")
    print("═" * 60)

    # --- Stage selection ---
    stage_choice = prompt_choice(
        "Which stages do you want to run?",
        [
            "Full pipeline (Domain → Pixel → Intelligence → Email)",
            "Stage 1 only — Domain Finder",
            "Stage 2 only — Pixel Checker",
            "Stage 3 only — Intelligence Engine",
            "Stage 4 only — Email Dispatch",
            "Stages 1 + 2 (Enrichment only, no email)",
            "Stages 3 + 4 (Intelligence + Email, skip enrichment)",
        ]
    )

    stages_map = {
        0: [1, 2, 3, 4],
        1: [1],
        2: [2],
        3: [3],
        4: [4],
        5: [1, 2],
        6: [3, 4],
    }
    selected_stages = stages_map[stage_choice]

    divider('Batch Settings')

    batch_size = prompt_int(
        "How many companies to process per stage",
        default=50
    )

    max_workers = 10
    if 2 in selected_stages:
        max_workers = prompt_int(
            "Pixel checker — parallel workers (higher = faster but more aggressive)",
            default=10
        )

    divider('Email Settings')

    test_mode  = False
    test_email = None

    if 4 in selected_stages:
        test_mode = prompt_yes_no(
            "Run in TEST MODE? (all emails sent to your address, not the lead)",
            default=True
        )
        if test_mode:
            ENV_TEST_EMAIL = os.getenv('TEST_EMAIL')
            test_email = ENV_TEST_EMAIL or input("Enter your test email address: ").strip()
            if not test_email:
                print("   No email entered — test mode disabled.")
                test_mode = False
            else:
                print(f"   Test email: {test_email}")

        if not test_mode:
            confirm = prompt_yes_no(
                "\n⚠️  PRODUCTION MODE: emails will go to real leads. Are you sure?",
                default=False
            )
            if not confirm:
                print("   Switching to test mode. Enter your test email address: ", end='')
                test_email = input().strip()
                test_mode  = bool(test_email)

    return {
        'selected_stages': selected_stages,
        'batch_size':      batch_size,
        'max_workers':     max_workers,
        'test_mode':       test_mode,
        'test_email':      test_email,
    }


def print_run_summary(config):
    """Prints a clear summary of what's about to run before execution."""
    stage_names = {
        1: 'Domain Finder',
        2: 'Pixel Checker',
        3: 'Intelligence Engine',
        4: 'Email Dispatch',
    }
    divider('Run Summary')
    print(f"  Stages     : {' → '.join(stage_names[s] for s in config['selected_stages'])}")
    print(f"  Batch size : {config['batch_size']} companies")
    if 2 in config['selected_stages']:
        print(f"  Workers    : {config['max_workers']} (pixel checker)")
    if 4 in config['selected_stages']:
        if config['test_mode']:
            print(f"  Email mode : TEST → all emails → {config['test_email']}")
        else:
            print(f"  Email mode : PRODUCTION → real leads")
    divider()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    config = collect_config()
    print_run_summary(config)

    go = prompt_yes_no("Start the pipeline now?", default=True)
    if not go:
        print("\nAborted. Nothing was run.")
        sys.exit(0)

    stage_names = {
        1: 'Domain Finder',
        2: 'Pixel Checker',
        3: 'Intelligence Engine',
        4: 'Email Dispatch',
    }

    for stage in config['selected_stages']:
        divider(f"Stage {stage}: {stage_names[stage]}")

        try:
            if stage == 1:
                run_enrichment_batch(batch_size=config['batch_size'])

            elif stage == 2:
                run_pixel_batch(
                    max_workers=config['max_workers'],
                    batch_size=config['batch_size']
                )

            elif stage == 3:
                run_intelligence_batch(batch_size=config['batch_size'])

            elif stage == 4:
                run_email_batch(
                    recipient_email_override=config['test_email'],
                    batch_size=config['batch_size']
                )

        except KeyboardInterrupt:
            print(f"\n\n⚠️  Stage {stage} interrupted by user. Pipeline stopped.")
            sys.exit(0)

        except Exception as e:
            print(f"\n❌ Stage {stage} failed with error: {e}")
            retry = prompt_yes_no("Continue to next stage anyway?", default=False)
            if not retry:
                print("Pipeline stopped.")
                sys.exit(1)

    divider('Pipeline Complete')
    print("  All selected stages finished successfully.")
    print("  Check your SQLite DB and output/plots/ for results.\n")


if __name__ == '__main__':
    main()