"""Versioned learned-knowledge lifecycle with explicit supersession and quarantine."""
from dataclasses import dataclass

_ALLOWED={"ACTIVE","QUARANTINED","REJECTED"}

@dataclass(frozen=True)
class KnowledgeVersion:
    knowledge_id: str
    version: int
    state: str
    supersedes_version: int | None = None
    execution_authority: bool = False

class KnowledgeLifecycle:
    def __init__(self, versions):
        self._versions={}
        for v in sorted(tuple(versions),key=lambda x:(x.knowledge_id,x.version)):
            if v.state not in _ALLOWED: raise ValueError("invalid knowledge state")
            if v.version<1: raise ValueError("version must be positive")
            key=(v.knowledge_id,v.version)
            if key in self._versions: raise ValueError("duplicate knowledge version")
            if v.version>1:
                prev=(v.knowledge_id,v.version-1)
                if prev not in self._versions: raise ValueError("knowledge version gap")
                if v.supersedes_version != v.version-1: raise ValueError("invalid supersession")
            self._versions[key]=v

    def status(self, knowledge_id, version):
        key=(str(knowledge_id),int(version))
        if key not in self._versions: raise KeyError(key)
        v=self._versions[key]
        newer=[x for (kid,ver),x in self._versions.items() if kid==key[0] and ver>key[1]]
        if newer: return "SUPERSEDED"
        return v.state

    def usable(self, knowledge_id, version):
        return self.status(knowledge_id,version)=="ACTIVE"
