"""Bridge selective replay deltas back into metacognitive governance."""
from dataclasses import dataclass

@dataclass(frozen=True)
class FeedbackAssessment:
    status: str
    recommendation: str
    execution_authority: bool = False

def evaluate_feedback(*,changed_hypotheses,unresolved_hypotheses,contradictions,unknowns):
    if int(contradictions)<0 or int(unknowns)<0:
        raise ValueError("counts must be non-negative")
    if contradictions:
        return FeedbackAssessment("BLOCKED","RESOLVE_CONTRADICTION",False)
    if unresolved_hypotheses or unknowns:
        return FeedbackAssessment("BLOCKED","REDUCE_UNKNOWNS",False)
    if changed_hypotheses:
        return FeedbackAssessment("RECHECK","REASSESS_REASONING",False)
    return FeedbackAssessment("STABLE","CONTINUE_TO_GOVERNANCE",False)
