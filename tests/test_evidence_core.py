import unittest

from lola_evidence import Confidence, Evidence, EvidenceLedger
from lola_hypothesis import Hypothesis


class EvidenceCoreTests(unittest.TestCase):
    def test_unknown_without_evidence(self):
        ledger = EvidenceLedger("sample.bin")
        finding = ledger.finding("sample finding")
        self.assertEqual(finding.confidence(), Confidence.UNKNOWN)

    def test_confidence_rises_with_independent_evidence(self):
        ledger = EvidenceLedger("sample.bin")
        statement = "format has executable code"
        ledger.add(statement, Evidence("header", "sample.bin", "header marker", tool="parser", weight=1.0))
        ledger.add(statement, Evidence("structure", "sample.bin", "code section", tool="structure", weight=1.0))
        ledger.add(statement, Evidence("disassembly", "sample.bin", "valid instructions", tool="disassembler", weight=1.0))
        finding = ledger.finding(statement)
        self.assertIn(finding.confidence(), {Confidence.HIGH, Confidence.VERIFIED})

    def test_contradiction_reduces_score(self):
        ledger = EvidenceLedger("sample.bin")
        statement = "candidate function matches expected behavior"
        positive = Evidence("static", "sample.bin", "matching references", tool="static", weight=0.9)
        negative = Evidence("runtime", "sample.bin", "behavior not observed", tool="runtime", weight=1.0)
        ledger.add(statement, positive)
        before = ledger.finding(statement).confidence_score()
        ledger.add(statement, negative, contradiction=True)
        after = ledger.finding(statement).confidence_score()
        self.assertLess(after, before)

    def test_hypothesis_reports_missing_evidence(self):
        ledger = EvidenceLedger("sample.bin")
        h = Hypothesis("candidate mapping", {"static", "runtime"})
        h.evaluate(ledger, [Evidence("static", "sample.bin", "xref", weight=0.8)])
        self.assertEqual(h.missing_evidence(), ["runtime"])


if __name__ == "__main__":
    unittest.main()
