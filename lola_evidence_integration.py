#!/usr/bin/env python3
"""Fail-open integration helpers for adding evidence analysis to Lola reports."""
from __future__ import annotations

from copy import deepcopy


def _unavailable(target: str, exc: Exception) -> dict:
    return {"status":"unavailable","target":target,"error":f"{type(exc).__name__}: {exc}"}


def enrich_apk_analysis(data: dict, target: str) -> dict:
    result=deepcopy(data) if isinstance(data,dict) else {"raw":data}
    try:
        from lola_evidence_adapters import apk_observations
        from lola_evidence_pipeline import safe_analyze
        rows=apk_observations(data)
        result["evidenceAnalysis"]=safe_analyze(target,rows)
    except Exception as exc:
        result["evidenceAnalysis"]=_unavailable(target,exc)
    return result


def enrich_code_report(report: dict, target: str) -> dict:
    result=deepcopy(report) if isinstance(report,dict) else {"raw":report}
    try:
        from lola_evidence_adapters import code_observations
        from lola_evidence_pipeline import safe_analyze
        rows=code_observations(report)
        result["evidenceAnalysis"]=safe_analyze(target,rows)
    except Exception as exc:
        result["evidenceAnalysis"]=_unavailable(target,exc)
    return result
