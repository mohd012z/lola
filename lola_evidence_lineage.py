"""Evidence-lineage DAG for ancestry-aware independence accounting."""
from dataclasses import dataclass

@dataclass(frozen=True)
class EvidenceNode:
    evidence_id: str
    origin_domain: str
    parent_ids: tuple = ()

class EvidenceLineageGraph:
    def __init__(self,nodes):
        self.nodes={n.evidence_id:n for n in nodes}
        if len(self.nodes)!=len(list(nodes)) if not isinstance(nodes,(list,tuple)) else False:
            raise ValueError("duplicate evidence id")
        for n in self.nodes.values():
            for p in n.parent_ids:
                if p not in self.nodes: raise ValueError("unknown evidence parent")
        visiting=set(); done=set()
        def visit(eid):
            if eid in visiting: raise ValueError("evidence lineage cycle")
            if eid in done: return
            visiting.add(eid)
            for p in self.nodes[eid].parent_ids: visit(p)
            visiting.remove(eid); done.add(eid)
        for eid in self.nodes: visit(eid)
    def _roots(self,eid):
        n=self.nodes[eid]
        if not n.parent_ids: return {eid}
        out=set()
        for p in n.parent_ids: out.update(self._roots(p))
        return out
    def independent_roots(self,evidence_ids):
        roots=set()
        for eid in evidence_ids:
            if eid not in self.nodes: raise ValueError("unknown evidence id")
            roots.update(self._roots(eid))
        return tuple(sorted(roots))
