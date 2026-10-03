"""Rollback journal and compensating recovery for failed post-commit knowledge verification."""
from dataclasses import dataclass
from copy import deepcopy

@dataclass(frozen=True)
class RollbackJournal:
    status: str
    transaction_id: str
    knowledge_id: str
    expected_version: int
    previous_active_version: int | None
    before_history: tuple
    execution_authority: bool = False

@dataclass(frozen=True)
class CompensationResult:
    status: str
    history: tuple
    recovery_record: dict
    execution_authority: bool = False

def _snapshot(history):
    return tuple(deepcopy(dict(r)) for r in history)

def create_rollback_journal(history,knowledge_id,expected_version,transaction_id):
    kid=str(knowledge_id)
    before=_snapshot(history)
    active=[r for r in before if str(r.get("knowledge_id",""))==kid and r.get("state")=="ACTIVE"]
    if len(active)>1:
        return RollbackJournal("BLOCKED",str(transaction_id),kid,int(expected_version),None,before,False)
    previous=int(active[0]["version"]) if active else None
    return RollbackJournal("READY",str(transaction_id),kid,int(expected_version),previous,before,False)

def compensate_failed_commit(current_history,journal,post_commit_valid):
    current=_snapshot(current_history)
    if post_commit_valid:
        return CompensationResult("NO_ROLLBACK",current,{"transaction_id":journal.transaction_id,"compensated":False,"reason":"POST_COMMIT_VERIFIED"},False)
    if journal.status!="READY":
        return CompensationResult("QUARANTINED",current,{"transaction_id":journal.transaction_id,"compensated":False,"reason":"JOURNAL_NOT_READY"},False)
    restored=_snapshot(journal.before_history)
    record={"transaction_id":journal.transaction_id,"knowledge_id":journal.knowledge_id,"failed_expected_version":journal.expected_version,"restored_version":journal.previous_active_version,"compensated":True,"reason":"POST_COMMIT_VERIFICATION_FAILED"}
    return CompensationResult("RESTORED",restored,record,False)
