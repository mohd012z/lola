"""Inspectable uncertainty calibration from evidence quality signals."""
from dataclasses import dataclass

@dataclass(frozen=True)
class UncertaintyAssessment:
    uncertainty: float
    evidence_count: int
    independent_origins: int
    unknowns: int
    contradictions: int
    failed_replays: int
    execution_authority: bool = False

def calibrate_uncertainty(*,evidence_count,independent_origins,unknowns,contradictions,failed_replays):
    vals=[evidence_count,independent_origins,unknowns,contradictions,failed_replays]
    if any(int(v)<0 for v in vals): raise ValueError("counts must be non-negative")
    e,i,u,c,f=map(int,vals)
    independence=(i/e) if e else 0.0
    penalty=min(1.0,0.15*u+0.25*c+0.35*f)
    uncertainty=max(0.0,min(1.0,1.0-(0.55*min(1.0,independence)+0.45*min(1.0,e/3.0))+penalty))
    return UncertaintyAssessment(round(uncertainty,6),e,i,u,c,f,False)
