"""Evidence-based gate for releasing recovered cognitive state from quarantine."""
from dataclasses import dataclass
from lola_feedback_loop import evaluate_feedback

@dataclass(frozen=True)
class QuarantineReleaseAssessment:
    status: str
    quarantine: bool
    recommendation: str
    execution_authority: bool = False

def assess_quarantine_release(*,trace_verified,changed_hypotheses,unresolved_hypotheses,contradictions,unknowns):
    if not trace_verified:
        return QuarantineReleaseAssessment("QUARANTINED",True,"VERIFY_TRACE",False)
    feedback=evaluate_feedback(changed_hypotheses=changed_hypotheses,unresolved_hypotheses=unresolved_hypotheses,contradictions=contradictions,unknowns=unknowns)
    if feedback.status=="BLOCKED":
        return QuarantineReleaseAssessment("QUARANTINED",True,feedback.recommendation,False)
    if feedback.status=="RECHECK":
        return QuarantineReleaseAssessment("RECHECK",True,feedback.recommendation,False)
    return QuarantineReleaseAssessment("RELEASE_CANDIDATE",False,"CONTINUE_TO_GOVERNANCE",False)
