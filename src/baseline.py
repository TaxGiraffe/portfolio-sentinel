"""Baseline store + the diff engine.

The whole product is the diff: 'these findings are NEW since the last scan'.
The judgment rules live here as code, not vibes:

  R1. Inconclusive results are NEVER breakage. A CDN challenge page, a 403, a
      JS-rendered shell - the auditor marks all of them inconclusive and the
      sentinel treats them as 'could not see', not 'is broken'.
  R2. Only presence-based findings can page a human on their own
      (broken_tel_link, broken_mailto, placeholder_text, dead links...).
      Absence-based findings (missing_*, no_*) require two consecutive
      confirmed sightings before they count - a stripped response can fake
      an absence, it cannot fake a presence.
  R3. A site that was fine and is now inconclusive is a WATCH, not an alert.
      A site with new high-severity presence findings is an ALERT.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

PRESENCE_SAFE = True  # presence-based findings alert immediately
ABSENCE_CONFIRMATIONS = 2  # absence-based findings need N consecutive sightings


def _is_absence(check: str) -> bool:
    return check.startswith("missing_") or check.startswith("no_")


def _is_inconclusive(row: dict) -> bool:
    if row.get("inconclusive"):
        return True
    return any(
        f.get("check", "").startswith("inconclusive") for f in row.get("findings", [])
    )


class Baseline:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.state = {}
        if self.path.exists():
            self.state = json.loads(self.path.read_text())

    def save(self) -> None:
        self.path.write_text(json.dumps(self.state, indent=2))

    def diff(self, rows: list[dict]) -> dict:
        """Compare a scan against the baseline. Returns alerts / watches / all-clear."""
        alerts, watches, cleared = [], [], []
        now = datetime.now(timezone.utc).isoformat()

        for row in rows:
            url = row.get("url", "?")
            prev = self.state.get(url, {"checks": {}, "inconclusive_streak": 0})

            if _is_inconclusive(row):
                prev["inconclusive_streak"] = prev.get("inconclusive_streak", 0) + 1
                if prev.get("checks") and prev["inconclusive_streak"] == 1:
                    watches.append({
                        "url": url,
                        "reason": "Site was readable before and is now inconclusive "
                                  "(bot-challenge/blocked). Not treated as breakage - R1.",
                    })
                self.state[url] = prev
                continue

            prev["inconclusive_streak"] = 0
            current, prior = {}, prev.get("checks", {})

            for f in row.get("findings", []):
                check = f.get("check", "")
                current[check] = {"severity": f.get("severity"), "detail": f.get("detail")}
                seen_before = check in prior
                if _is_absence(check):
                    sightings = prior.get(check, {}).get("sightings", 0) + 1
                    current[check]["sightings"] = sightings
                    if not seen_before:
                        continue  # first sighting of an absence: hold - R2
                    if sightings == ABSENCE_CONFIRMATIONS and f.get("severity") in ("high", "medium"):
                        alerts.append({"url": url, "check": check, "new": True,
                                       "confirmed_absence": True, **f})
                else:
                    if not seen_before and f.get("severity") == "high":
                        alerts.append({"url": url, "check": check, "new": True, **f})

            for check in prior:
                if check not in current and not check.startswith("inconclusive"):
                    cleared.append({"url": url, "check": check})

            prev["checks"] = current
            prev["last_scan"] = now
            self.state[url] = prev

        return {"alerts": alerts, "watches": watches, "cleared": cleared,
                "scanned": len(rows), "at": now}
