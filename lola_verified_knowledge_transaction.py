"""Fail-closed coordinator for journaled commit, post-commit verification, compensation and restore verification."""
from dataclasses import dataclass
from lola_atomic_knowledge_transaction import commit_candidate
from lola_post_commit_verifier import verify_committed_knowledge
from lola_knowledge_rollback_journal import create_rollback_journal, compensate_failed_commit

@dataclass(frozen=True)
class VerifiedKnowledgeTransactionResult:
    status: str
    history: tuple
    post_commit_valid: bool
    restore_valid: bool
    recovery_record: dict
    execution_authority: bool = False

def _restore_valid(history,journal):
    if journal.previous_active_version is None:
        return tuple(history)==tuple(journal.before_history)
    rows=[r for r in history if str(r.get("knowledge_id",""))==journal.knowledge_id]
    active=[r for r in rows if r.get("state")=="ACTIVE"]
    return len(active)==1 and int(active[0].get("version",-1))==journal.previous_active_version and tuple(history)==tuple(journal.before_history)

def execute_verified_transaction(history,candidate,transaction_id,expected_fingerprint_override=None):
    before=tuple(dict(r) for r in history)
    if getattr(candidate,"status",None)!="CANDIDATE" or candidate.version is None:
        return VerifiedKnowledgeTransactionResult("REJECTED",before,False,False,{"compensated":False,"reason":"INVALID_CANDIDATE"},False)
    journal=create_rollback_journal(before,candidate.knowledge_id,candidate.version,transaction_id)
    if journal.status!="READY":
        return VerifiedKnowledgeTransactionResult("QUARANTINED",before,False,False,{"compensated":False,"reason":"JOURNAL_NOT_READY"},False)
    committed=commit_candidate(before,candidate)
    if committed.status!="COMMITTED":
        return VerifiedKnowledgeTransactionResult(committed.status,committed.history,False,False,{"compensated":False,"reason":committed.reason},False)
    expected=candidate.fingerprint if expected_fingerprint_override is None else expected_fingerprint_override
    verification=verify_committed_knowledge(committed.history,candidate.knowledge_id,candidate.version,expected)
    if verification.valid:
        return VerifiedKnowledgeTransactionResult("VERIFIED_COMMIT",committed.history,True,False,{"compensated":False,"reason":"POST_COMMIT_VERIFIED"},False)
    compensation=compensate_failed_commit(committed.history,journal,post_commit_valid=False)
    restored_ok=_restore_valid(compensation.history,journal)
    status="RESTORED_VERIFIED" if compensation.status=="RESTORED" and restored_ok else "QUARANTINED"
    return VerifiedKnowledgeTransactionResult(status,compensation.history,False,restored_ok,compensation.recovery_record,False)
