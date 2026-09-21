"""Fallback bot coordinator for unresolved EX4/EX5 diagnostics.

Coordinates evidence-producing specialists. Each bot may answer, skip, or ask
for more evidence. The coordinator never treats inference as recovered source.
"""
from __future__ import annotations
from pathlib import Path
from lola_ex_problem_router import diagnose
from lola_mt5_mcp_bridge import ask as ask_mt5

def evidence_request(packet):
    unresolved=packet.get("unresolved",[])
    options=[]
    if any("source" in x.lower() for x in unresolved):
        options.append({"id":"source","label":"Add matching MQ4/MQ5/MQH source","why":"enables source-level compile and reference checks"})
    if any("log" in x.lower() for x in unresolved):
        options += [
          {"id":"experts-log","label":"Add Experts/Journal log","why":"captures runtime errors and initialization failures"},
          {"id":"tester-log","label":"Add Strategy Tester report/log","why":"captures reproducible tester behavior"}]
    options += [
      {"id":"screenshot","label":"Add error screenshot/message","why":"preserves the exact visible MetaTrader error"},
      {"id":"expected","label":"Describe expected vs actual behavior","why":"lets fallback bots test a concrete hypothesis"}]
    return {"optional":True,"message":"More evidence can improve confidence; fallback bots can continue with current evidence.",
            "options":options}

def fallback_plan(path,question=None):
    local=diagnose(path,question,ask_ai=False)
    if not local.get("ok"):return local
    packet=local["packet"]
    return {"schema":"Lola-EX-Fallback-1","local":local,"evidence_request":evidence_request(packet),
            "bots":[
              {"id":"local-evidence","status":"complete","role":"hash/signature/string/source/log evidence"},
              {"id":"source-reference","status":"ready" if any(x.get("type")=="SOURCE" and x.get("available") for x in packet["evidence"]) else "waiting-evidence",
               "role":"compare available MQ4/MQ5/MQH reference source"},
              {"id":"runtime-log","status":"ready" if any(x.get("type")=="RUNTIME" and x.get("available") for x in packet["evidence"]) else "waiting-evidence",
               "role":"classify MetaTrader runtime/compiler/tester errors"},
              {"id":"mt5-ai","status":"available-if-configured","role":"cross-check bounded evidence with authorized MT5 AI/MCP"},
              {"id":"help","status":"fallback","role":"produce unresolved packet for another specialist"}],
            "policy":{"continue_without_optional_evidence":True,
                      "stop_on":["unsupported claim","request to bypass EX4/EX5 protection"],
                      "labels":["OBSERVED","SOURCE","RUNTIME","TESTER","AI_SUGGESTION","INFERRED","UNRESOLVED"]}}

def run_fallback(path,question=None,use_mt5=True):
    plan=fallback_plan(path,question)
    if not plan.get("schema"):return plan
    attempts=[]
    local=plan["local"]
    attempts.append({"bot":"local-evidence","result":local})
    if use_mt5:
        attempts.append({"bot":"mt5-ai","result":ask_mt5(Path(path),question or
          "Use only the supplied EX4/EX5 evidence. Diagnose supported causes and next checks; label inference and do not claim source recovery.")})
    ai_reviewed=any(a["result"].get("ok") and a["bot"]=="mt5-ai" for a in attempts if isinstance(a.get("result"),dict))
    return {"ok":True,"plan":plan,"attempts":attempts,
            "status":"AI_REVIEWED" if ai_reviewed else "NEEDS_HELP",
            "next":{"command":"/help","packet":local.get("packet"),"evidence_options":plan["evidence_request"]}
                   if not ai_reviewed else {"action":"compare AI suggestion against observed/runtime evidence before marking resolved"}}
