"""Portfolio Sentinel - a Strands agent that watches a web agency's client sites
and only speaks when something is verifiably broken.

The repetitive, judgment-heavy task it removes: a small agency maintains 20-100
client sites. Nobody re-checks them after launch. The first person to notice a
dead call button is usually the client - or nobody. Checking is boring, constant,
and judgment-heavy (a 403 is not an outage; a challenge page is not a missing H1).

The sentinel runs the check loop in the background and applies the judgment:
  - scans the portfolio with a defect auditor that marks unreadable pages
    INCONCLUSIVE instead of guessing (champ1918/local-business-website-auditor)
  - diffs against the last known state (src/baseline.py, rules R1-R3)
  - asks the model to triage the diff and write the client-ready note
  - surfaces ONLY when there is a real decision for a human to make

Run:
    export APIFY_TOKEN=...          # Apify Console > API & Integrations
    # AWS credentials for Bedrock (or set STRANDS_MODEL for another provider)
    python src/sentinel.py portfolio.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from strands import Agent, tool

sys.path.insert(0, str(Path(__file__).parent))
from auditor_client import audit_urls_rest  # noqa: E402
from baseline import Baseline  # noqa: E402

BASELINE_PATH = Path("sentinel_state.json")
ALERT_PATH = Path("ALERTS.md")


@tool
def scan_portfolio(portfolio_file: str) -> str:
    """Scan every site in the portfolio file with the website-defect auditor.

    Args:
        portfolio_file: path to a JSON file: {"agency": str, "sites": [{"client": str, "url": str}]}

    Returns:
        JSON string of raw audit rows (one per site) including htmlLength,
        rawTitle, findings and inconclusive markers.
    """
    cfg = json.loads(Path(portfolio_file).read_text())
    urls = [s["url"] for s in cfg["sites"]]
    rows = audit_urls_rest(urls)
    return json.dumps(rows)


@tool
def diff_against_baseline(scan_rows_json: str) -> str:
    """Diff a scan against the stored baseline and apply the judgment rules.

    R1: inconclusive is never breakage. R2: absence-based findings need two
    confirmed sightings; presence-based high-severity findings alert at once.
    R3: readable-then-inconclusive is a watch, not an alert.

    Args:
        scan_rows_json: the JSON string returned by scan_portfolio.

    Returns:
        JSON string: {"alerts": [...], "watches": [...], "cleared": [...], "scanned": n}
    """
    baseline = Baseline(BASELINE_PATH)
    result = baseline.diff(json.loads(scan_rows_json))
    baseline.save()
    return json.dumps(result)


@tool
def surface_to_human(markdown_report: str) -> str:
    """Deliver a report to the agency owner. Only call this when there is a real
    decision to make - a verified new defect or a cleared one worth invoicing.

    Args:
        markdown_report: the finished, client-ready markdown note.

    Returns:
        confirmation string with the delivery path.
    """
    ALERT_PATH.write_text(markdown_report)
    print("\n" + "=" * 60)
    print(markdown_report)
    print("=" * 60)
    return f"Delivered to {ALERT_PATH.resolve()}"


SYSTEM_PROMPT = """You are Portfolio Sentinel, a background agent for a small web-design
agency. Your job is to check every client site, compare against the last known state,
and interrupt a human ONLY when there is a real decision to make.

Hard rules - these come from production incidents, do not soften them:
1. INCONCLUSIVE is never breakage. A 403, a timeout, a bot-challenge page, a
   JS-rendered shell: the auditor could not see the site. Never tell the owner a
   site is broken based on a page nobody actually received.
2. Presence beats absence. A malformed tel: link IS on the page - report it.
   A "missing" meta tag might be a CDN stub lying to the crawler - it needs two
   confirmed sightings before you mention it.
3. Silence is the product. If the diff has no alerts, do NOT call surface_to_human.
   Print a one-line all-clear and stop. The owner's attention is the scarcest
   resource in the system.

Workflow: scan_portfolio -> diff_against_baseline -> IF alerts exist, write a
client-ready note (which client, which site, what broke, how the owner can verify
it in ten seconds, suggested next step) and call surface_to_human. Watches are
mentioned in one line each, never as alarms. Cleared findings are worth one
sentence - fixed defects are billable proof of work."""


def main() -> None:
    portfolio = sys.argv[1] if len(sys.argv) > 1 else "portfolio.json"
    agent = Agent(
        system_prompt=SYSTEM_PROMPT,
        tools=[scan_portfolio, diff_against_baseline, surface_to_human],
    )
    agent(
        f"Run the sentinel pass over {portfolio}. Remember: only surface if a "
        f"human decision is genuinely needed."
    )


if __name__ == "__main__":
    main()
