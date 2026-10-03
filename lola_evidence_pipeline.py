#!/usr/bin/env python3
"""Orchestrate normalized observations into additive Lola evidence analysis."""
from __future__ import annotations

from collections.abc import Iterable
from lola_evidence import Evidence, EvidenceLedger


def analyze_observations(target: str, observations: list[Evidence], *, expected_kinds: set[str] | None=None,
                         contradictions: list[Evidence] | None=None) -> dict:
    if not isinstance(observations,list) or not all(isinstance(x,Evidence) for x in observations):
        raise TypeError("observations must be a list of Evidence")
    ledger=EvidenceLedger(target)
    for row in observations:
        ledger.add(f"Observed {row.kind}: {row.observation}",row)
    contradictions=contradictions or []
    if contradictions:
        if observations:
            statement=f"Observed {observations[0].kind}: {observations[0].observation}"
        else:
            statement="Evidence hypothesis"
        for row in contradictions:
            if not isinstance(row,Evidence): raise TypeError("contradictions must contain Evidence")
            ledger.add(statement,row,contradiction=True)
    present={x.kind for x in observations}
    missing=sorted((expected_kinds or set())-present)
    if missing:
        ledger.finding("Expected evidence coverage")
    summary=ledger.summary()
    return {"status":"ok","target":target,"observationCount":len(observations),"missingEvidence":missing,
            "counts":summary["counts"],"findings":summary["findings"]}


def safe_analyze(target: str, observations, **kwargs) -> dict:
    try:
        return analyze_observations(target,observations,**kwargs)
    except Exception as exc:
        return {"status":"unavailable","target":target,"error":f"{type(exc).__name__}: {exc}"}
