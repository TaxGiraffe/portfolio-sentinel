"""Offline tests for the judgment rules - no network, no tokens."""
import json, sys
sys.path.insert(0, "src")
from baseline import Baseline

def run():
    import tempfile, os
    tmp = tempfile.mktemp()
    b = Baseline(tmp)

    # Scan 1: one presence-high (alerts NOW), one absence-medium (held - R2)
    scan1 = [{"url": "https://a.com", "findings": [
        {"check": "broken_tel_link", "severity": "high", "detail": "tel has 3 digits"},
        {"check": "missing_h1", "severity": "medium", "detail": "no h1"},
    ]}]
    d1 = b.diff(scan1); b.save()
    assert len(d1["alerts"]) == 1 and d1["alerts"][0]["check"] == "broken_tel_link", d1
    print("R2/presence: immediate alert on presence-high, absence held ... ok")

    # Scan 2: absence seen a 2nd consecutive time -> now alerts
    d2 = Baseline(tmp).diff(scan1)
    assert any(a["check"] == "missing_h1" and a.get("confirmed_absence") for a in d2["alerts"]), d2
    print("R2/absence: second confirmed sighting alerts ... ok")

    # Scan 3: site goes inconclusive -> watch, never alert (R1)
    b2 = Baseline(tmp)
    d3 = b2.diff([{"url": "https://a.com", "inconclusive": True, "findings": [
        {"check": "inconclusive_stub", "severity": "low", "detail": "12kb challenge page"}]}])
    assert d3["alerts"] == [] and len(d3["watches"]) == 1, d3
    print("R1: readable->inconclusive is a watch, not an alert ... ok")

    # Scan 4: site readable again, defect gone -> cleared
    b3 = Baseline(tmp)
    d4 = b3.diff([{"url": "https://a.com", "findings": []}])
    assert any(c["check"] == "broken_tel_link" for c in d4["cleared"]), d4
    print("R3/cleared: fixed defects reported as cleared ... ok")

    os.unlink(tmp)
    print("\nALL JUDGMENT-RULE TESTS PASS")

run()
