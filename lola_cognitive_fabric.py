#!/usr/bin/env python3
"""Hybrid cognitive fabric for Lola / Kernel_AI / IN_AI."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable
import hashlib, json, threading

class Kind(str, Enum):
    OBSERVATION="observation"; STATE="state"; QUERY="query"; COMMAND="command"; RESULT="result"; EVIDENCE="evidence"; ERROR="error"; HEARTBEAT="heartbeat"; CAPABILITY="capability"
class PathClass(str, Enum): FAST="fast"; COGNITIVE="cognitive"; DURABLE="durable"

@dataclass(frozen=True)
class KIPEnvelope:
    kind:str; topic:str; source:str; payload:dict[str,Any]; id:str=""; task_id:str=""; correlation_id:str=""; trace_id:str=""; span_id:str=""; parent_span_id:str=""; timestamp:str=field(default_factory=lambda:datetime.now(timezone.utc).isoformat()); sequence:int=0; reliability:float=.5; priority:int=2; direct:bool=False; durable:bool=False; evidence_grade:str=""; evidence_id:str=""; provenance:dict[str,Any]=field(default_factory=dict); version:str="1.2"
    def __post_init__(self):
        if not self.id:
            raw=f"{self.source}|{self.topic}|{self.timestamp}|{self.sequence}|{self.payload}"; object.__setattr__(self,"id",hashlib.sha256(raw.encode()).hexdigest()[:20])
        if not self.trace_id: object.__setattr__(self,"trace_id",self.correlation_id or self.task_id or self.id)
        if not self.span_id: object.__setattr__(self,"span_id",self.id[:16])
        object.__setattr__(self,"reliability",max(0.,min(1.,float(self.reliability)))); object.__setattr__(self,"priority",max(0,min(4,int(self.priority))))
    def to_dict(self): return asdict(self)

@dataclass
class SourceProfile:
    source_id:str; capabilities:set[str]=field(default_factory=set); reliability:float=.5; last_seen:str=""; transport:str="internal"
class SourceRegistry:
    def __init__(self): self.sources={}
    def register(self,source_id,capabilities,*,reliability=.5,transport="internal"):
        p=SourceProfile(source_id,set(capabilities),max(0.,min(1.,reliability)),datetime.now(timezone.utc).isoformat(),transport); self.sources[source_id]=p; return p
    def select(self,capability): return sorted((s for s in self.sources.values() if capability in s.capabilities),key=lambda s:s.reliability,reverse=True)

class EventStore:
    def __init__(self,path):
        self.path=Path(path); self._lock=threading.Lock(); self._seen=set()
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:self._seen.add(json.loads(line)["id"])
                except (ValueError,KeyError,TypeError):pass
    def append(self,event):
        if event.id in self._seen:return False
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self._lock:
            if event.id in self._seen:return False
            with self.path.open("a",encoding="utf-8") as fh:fh.write(json.dumps(event.to_dict(),ensure_ascii=False,sort_keys=True)+"\n")
            self._seen.add(event.id)
        return True
    def replay(self,task_id=""):
        if not self.path.exists():return []
        out=[]
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:item=json.loads(line)
            except ValueError:continue
            if not task_id or item.get("task_id")==task_id:out.append(item)
        return out

@dataclass
class Observation:
    event_id:str; source:str; topic:str; payload:dict[str,Any]; reliability:float; direct:bool; timestamp:str; evidence_grade:str=""; evidence_id:str=""; provenance:dict[str,Any]=field(default_factory=dict)
@dataclass
class Hypothesis:
    hypothesis_id:str; statement:str; predicts:dict[str,Any]=field(default_factory=dict); status:str="PROPOSED"
@dataclass
class CognitiveState:
    task_id:str; objective:str=""; observations:list[Observation]=field(default_factory=list); unknowns:set[str]=field(default_factory=set); assumptions:set[str]=field(default_factory=set); contradictions:list[str]=field(default_factory=list); hypotheses:dict[str,Hypothesis]=field(default_factory=dict); predictions:dict[str,str]=field(default_factory=dict); world:dict[str,Any]=field(default_factory=dict); verified_claims:set[str]=field(default_factory=set)

class HybridRouter:
    FAST_PREFIXES=("heartbeat.","progress.","telemetry."); COGNITIVE_PREFIXES=("error.","runtime.","build.failure","test.failure","evidence.")
    def classify(self,event):
        p=set()
        if event.durable or event.kind in {Kind.EVIDENCE.value,Kind.RESULT.value,Kind.ERROR.value}:p.add(PathClass.DURABLE)
        if event.topic.startswith(self.FAST_PREFIXES) or event.kind==Kind.HEARTBEAT.value:p.add(PathClass.FAST)
        if event.topic.startswith(self.COGNITIVE_PREFIXES) or event.kind in {Kind.OBSERVATION.value,Kind.EVIDENCE.value,Kind.ERROR.value}:p.add(PathClass.COGNITIVE)
        if not p:p.add(PathClass.FAST)
        return p
class MetaController:
    @staticmethod
    def metrics(state):
        o=state.observations; direct=sum(1 for x in o if x.direct); avg=sum(x.reliability for x in o)/len(o) if o else 0.; cr=len(state.contradictions)/max(1,len(o)); fuse=cr>.25 or avg<.45
        return {"observations":len(o),"unknowns":len(state.unknowns),"assumptions":len(state.assumptions),"contradictions":len(state.contradictions),"average_reliability":round(avg,4),"evidence_coverage":round(direct/max(1,len(o)),4),"contradiction_rate":round(cr,4),"epistemic_fuse":fuse}
    def decision(self,state):
        m=self.metrics(state)
        if m["epistemic_fuse"]:return "CROSSCHECK"
        if state.unknowns:return "CONTINUE"
        if state.assumptions:return "FALSIFY"
        return "VERIFY"

class CognitiveFabric:
    def __init__(self,event_store): self.registry=SourceRegistry(); self.router=HybridRouter(); self.meta=MetaController(); self.events=EventStore(event_store); self.states={}; self._processed=set()
    def state(self,task_id,objective=""):
        if task_id not in self.states:self.states[task_id]=CognitiveState(task_id,objective)
        elif objective:self.states[task_id].objective=objective
        return self.states[task_id]
    def ingest(self,event):
        paths=self.router.classify(event)
        if event.id in self._processed:return {"accepted":False,"reason":"duplicate","id":event.id}
        self._processed.add(event.id)
        if PathClass.DURABLE in paths:self.events.append(event)
        s=self.state(event.task_id or "global")
        if PathClass.COGNITIVE in paths:
            s.observations.append(Observation(event.id,event.source,event.topic,dict(event.payload),event.reliability,event.direct,event.timestamp,event.evidence_grade,event.evidence_id,dict(event.provenance))); self._update_world(s,event)
        return {"accepted":True,"id":event.id,"trace_id":event.trace_id,"paths":sorted(x.value for x in paths),"meta":self.meta.metrics(s),"next":self.meta.decision(s)}
    @staticmethod
    def _update_world(s,event):
        entity,prop=str(event.payload.get("entity","")),str(event.payload.get("property",""))
        if not entity or not prop or "value" not in event.payload:return
        key,value=f"{entity}.{prop}",event.payload["value"]; previous=s.world.get(key)
        if previous is not None and previous!=value and event.direct:s.contradictions.append(f"{key}: {previous!r} != {value!r}")
        s.world[key]=value;s.unknowns.discard(key)
    def propose_hypothesis(self,task_id,hypothesis_id,statement,*,predicts):
        s=self.state(task_id); h=Hypothesis(hypothesis_id,statement,dict(predicts));s.hypotheses[hypothesis_id]=h;s.unknowns.update(k for k in predicts if k not in s.world);return h
    def evaluate_hypothesis(self,task_id,hypothesis_id):
        s=self.state(task_id);h=s.hypotheses[hypothesis_id];missing=[k for k in h.predicts if k not in s.world];conflicts={k:{"expected":v,"actual":s.world.get(k)} for k,v in h.predicts.items() if k in s.world and s.world[k]!=v}
        if missing:h.status="UNRESOLVED"
        elif conflicts:h.status="FALSIFIED"
        else:h.status="SUPPORTED"
        return {"id":hypothesis_id,"status":h.status,"missing":missing,"conflicts":conflicts}
    def verify_hypothesis(self,task_id,hypothesis_id,*,corroboration,validators):
        s=self.state(task_id);h=s.hypotheses[hypothesis_id]
        if h.status!="SUPPORTED":return {"id":hypothesis_id,"status":h.status,"verified":False,"reason":"not_supported"}
        if self.meta.metrics(s)["epistemic_fuse"]:return {"id":hypothesis_id,"status":"SUPPORTED","verified":False,"reason":"epistemic_fuse"}
        if getattr(corroboration,"conflicts",()):return {"id":hypothesis_id,"status":"SUPPORTED","verified":False,"reason":"evidence_conflict"}
        if len(getattr(corroboration,"independent_sources",()))<2:return {"id":hypothesis_id,"status":"SUPPORTED","verified":False,"reason":"insufficient_corroboration"}
        if not getattr(corroboration,"evidence_ids",()):return {"id":hypothesis_id,"status":"SUPPORTED","verified":False,"reason":"missing_provenance"}
        if not validators or not all(bool(v) for v in validators.values()):return {"id":hypothesis_id,"status":"SUPPORTED","verified":False,"reason":"validator_failed"}
        h.status="VERIFIED";s.verified_claims.add(hypothesis_id);return {"id":hypothesis_id,"status":"VERIFIED","verified":True,"evidence_ids":list(corroboration.evidence_ids),"validators":dict(validators)}
    def rank_unknowns(self,task_id,*,costs=None):
        s=self.state(task_id);costs=costs or {};r=[]
        for u in s.unknowns:
            sources=self.registry.select(u);rel=sources[0].reliability if sources else .35;cost=max(0.,min(1.,float(costs.get(u,.5))));score=rel*(1.-.6*cost);r.append({"unknown":u,"score":round(score,4),"source":sources[0].source_id if sources else "","cost":cost})
        return sorted(r,key=lambda x:(-x["score"],x["unknown"]))
    def causal_delta(self,task_id,expected):
        s=self.state(task_id)
        for i,(key,wanted) in enumerate(expected):
            actual=s.world.get(key,"<UNKNOWN>")
            if actual!=wanted:return {"index":i,"key":key,"expected":wanted,"actual":actual}
        return {"index":-1,"status":"no_divergence"}
    def snapshot(self,task_id):
        s=self.state(task_id);return {"task_id":s.task_id,"objective":s.objective,"world":dict(s.world),"unknowns":sorted(s.unknowns),"assumptions":sorted(s.assumptions),"contradictions":list(s.contradictions),"hypotheses":{k:asdict(v) for k,v in s.hypotheses.items()},"verified_claims":sorted(s.verified_claims),"meta":self.meta.metrics(s),"next":self.meta.decision(s)}
