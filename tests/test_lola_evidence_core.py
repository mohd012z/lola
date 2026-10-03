import json
import tempfile
import unittest
from pathlib import Path
from lola_evidence_core import EvidenceCoreLedger, EvidenceIntegrityError, event_digest

class EvidenceCoreLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)/"evidence.jsonl"; self.ledger=EvidenceCoreLedger(self.path)
    def tearDown(self): self.tmp.cleanup()

    def test_append_builds_hash_chain_and_trace(self):
        first=self.ledger.append(trace_id="trace-1",event_type="source",source_hash="a"*64,event_id="event-1",timestamp="2026-09-29T00:00:00+00:00")
        second=self.ledger.append(trace_id="trace-1",event_type="decision",source_hash="a"*64,decision="DENY",event_id="event-2",timestamp="2026-09-29T00:00:01+00:00")
        self.assertEqual(second.previous_hash,first.event_hash)
        self.assertEqual([x.event_id for x in self.ledger.trace("trace-1")],["event-1","event-2"])

    def test_hash_is_canonical(self):
        a={"b":2,"a":1}; b={"a":1,"b":2}
        self.assertEqual(event_digest(a),event_digest(b))

    def test_tampered_event_is_rejected(self):
        self.ledger.append(trace_id="trace",event_type="decision",source_hash="b"*64,decision="DENY")
        row=json.loads(self.path.read_text()); row["decision"]="ALLOW"
        self.path.write_text(json.dumps(row)+"\n")
        with self.assertRaises(EvidenceIntegrityError): self.ledger.verify()

    def test_broken_chain_is_rejected(self):
        self.ledger.append(trace_id="trace",event_type="source",source_hash="c"*64)
        self.ledger.append(trace_id="trace",event_type="decision",source_hash="c"*64)
        rows=[json.loads(x) for x in self.path.read_text().splitlines()]; rows[1]["previous_hash"]="f"*64
        unsigned=dict(rows[1]); unsigned.pop("event_hash"); rows[1]["event_hash"]=event_digest(unsigned)
        self.path.write_text("\n".join(json.dumps(x) for x in rows)+"\n")
        with self.assertRaises(EvidenceIntegrityError): self.ledger.verify()

    def test_corrupted_ledger_cannot_be_extended(self):
        self.path.write_text("not-json\n")
        with self.assertRaises(EvidenceIntegrityError): self.ledger.append(trace_id="trace",event_type="source",source_hash="d"*64)

if __name__ == "__main__": unittest.main()
