"""Lineage-aware episodic compilation: episode frequency cannot inflate evidence independence."""
from dataclasses import dataclass
from lola_evidence_lineage import EvidenceNode, EvidenceLineageGraph

@dataclass(frozen=True)
class LineageExperience:
    episode_ids: tuple
    independent_root_ids: tuple
    independent_origin_domains: tuple
    effective_independent_origins: int
    counterexample_episode_ids: tuple
    status: str = "ANALYZED"

def compile_lineage_experience(node_records, episodes):
    nodes=tuple(EvidenceNode(str(n["evidence_id"]),str(n.get("origin_domain","")),tuple(map(str,n.get("parent_ids") or ()))) for n in node_records)
    graph=EvidenceLineageGraph(nodes)
    eps=tuple(sorted(episodes,key=lambda e:str(e.get("episode_id",""))))
    evidence_ids=tuple(str(eid) for e in eps for eid in (e.get("evidence_ids") or ()))
    roots=graph.independent_roots(evidence_ids) if evidence_ids else ()
    domains=tuple(sorted({graph.nodes[r].origin_domain for r in roots if graph.nodes[r].origin_domain}))
    counterexamples=tuple(str(e.get("episode_id","")) for e in eps if str(e.get("outcome","")) in {"FAILED","FALSIFIED"})
    return LineageExperience(tuple(str(e.get("episode_id","")) for e in eps),roots,domains,len(roots),counterexamples)
