"""Post-commit invariant and retrieval/read-back verification for versioned knowledge."""
from dataclasses import dataclass

@dataclass(frozen=True)
class PostCommitVerification:
    valid: bool
    status: str
    reason: str
    execution_authority: bool = False

def verify_committed_knowledge(history,knowledge_id,expected_version,expected_fingerprint=None):
    kid=str(knowledge_id); version=int(expected_version)
    rows=[r for r in history if str(r.get("knowledge_id",""))==kid]
    active=[r for r in rows if r.get("state")=="ACTIVE"]
    if len(active)!=1 or int(active[0].get("version",-1))!=version:
        return PostCommitVerification(False,"INVARIANT_FAILURE","EXPECTED_SINGLE_ACTIVE_VERSION",False)
    current=active[0]
    if expected_fingerprint is not None and current.get("fingerprint")!=expected_fingerprint:
        return PostCommitVerification(False,"READBACK_MISMATCH","FINGERPRINT_MISMATCH",False)
    previous=current.get("supersedes_version")
    if previous is not None:
        matches=[r for r in rows if int(r.get("version",-1))==int(previous)]
        if len(matches)!=1 or matches[0].get("state")!="SUPERSEDED":
            return PostCommitVerification(False,"INVARIANT_FAILURE","SUPERSEDED_CHAIN_BROKEN",False)
    versions=[int(r.get("version",-1)) for r in rows]
    if len(versions)!=len(set(versions)):
        return PostCommitVerification(False,"INVARIANT_FAILURE","DUPLICATE_VERSION",False)
    return PostCommitVerification(True,"VERIFIED","POST_COMMIT_INVARIANTS_HOLD",False)
