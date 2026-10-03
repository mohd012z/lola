"""Immutable-style transaction event ledger for idempotency, replay and deterministic resume."""
from dataclasses import dataclass
from copy import deepcopy

@dataclass(frozen=True)
class LedgerDecision:
    status: str
    ledger: object
    transaction_id: str | None = None
    existing_transaction_id: str | None = None
    terminal_status: str | None = None
    result: object = None
    last_event: str | None = None
    execution_authority: bool = False

class TransactionEventLedger:
    def __init__(self, events=()):
        self.events=tuple(deepcopy(tuple(events)))

    def _with(self,event):
        return TransactionEventLedger(self.events+(deepcopy(event),))

    def _events_for(self,transaction_id):
        tid=str(transaction_id)
        return tuple(e for e in self.events if e.get("transaction_id")==tid)

    def begin(self,transaction_id,idempotency_key):
        tid=str(transaction_id); key=str(idempotency_key)
        matches=[e for e in self.events if e.get("idempotency_key")==key]
        if matches:
            existing=matches[0]["transaction_id"]
            terminal=[e for e in self._events_for(existing) if e.get("event")=="COMPLETE"]
            if terminal:
                last=terminal[-1]
                return LedgerDecision("REPLAY",self,tid,existing,last.get("status"),deepcopy(last.get("result")),"COMPLETE",False)
            return LedgerDecision("DUPLICATE",self,tid,existing,None,None,matches[-1].get("event"),False)
        event={"event":"BEGIN","transaction_id":tid,"idempotency_key":key}
        ledger=self._with(event)
        return LedgerDecision("STARTED",ledger,tid,None,None,None,"BEGIN",False)

    def complete(self,transaction_id,status,result=None):
        tid=str(transaction_id)
        tx=self._events_for(tid)
        if not tx:
            return LedgerDecision("UNKNOWN_TRANSACTION",self,tid,None,None,None,None,False)
        if any(e.get("event")=="COMPLETE" for e in tx):
            last=[e for e in tx if e.get("event")=="COMPLETE"][-1]
            return LedgerDecision("REPLAY",self,tid,tid,last.get("status"),deepcopy(last.get("result")),"COMPLETE",False)
        key=tx[0].get("idempotency_key")
        event={"event":"COMPLETE","transaction_id":tid,"idempotency_key":key,"status":str(status),"result":deepcopy(result)}
        ledger=self._with(event)
        return LedgerDecision("COMPLETED",ledger,tid,None,str(status),deepcopy(result),"COMPLETE",False)

    def resume(self,transaction_id):
        tid=str(transaction_id); tx=self._events_for(tid)
        if not tx:
            return LedgerDecision("UNKNOWN_TRANSACTION",self,tid,None,None,None,None,False)
        terminal=[e for e in tx if e.get("event")=="COMPLETE"]
        if terminal:
            last=terminal[-1]
            return LedgerDecision("REPLAY",self,tid,tid,last.get("status"),deepcopy(last.get("result")),"COMPLETE",False)
        return LedgerDecision("RESUME",self,tid,tid,None,None,tx[-1].get("event"),False)
