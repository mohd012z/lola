import unittest
from lola_evidence_lineage import EvidenceNode, EvidenceLineageGraph

class EvidenceLineageTests(unittest.TestCase):
    def test_shared_ancestor_collapses_independence(self):
        g=EvidenceLineageGraph([
            EvidenceNode("root","origin:a",()),
            EvidenceNode("b","channel:b",("root",)),
            EvidenceNode("c","channel:c",("root",)),
        ])
        self.assertEqual(g.independent_roots(["b","c"]),("root",))

    def test_distinct_roots_remain_independent(self):
        g=EvidenceLineageGraph([EvidenceNode("a","o:a",()),EvidenceNode("b","o:b",())])
        self.assertEqual(g.independent_roots(["a","b"]),("a","b"))

    def test_cycle_is_rejected(self):
        with self.assertRaises(ValueError):
            EvidenceLineageGraph([EvidenceNode("a","o:a",("b",)),EvidenceNode("b","o:b",("a",))])

    def test_unknown_parent_is_rejected(self):
        with self.assertRaises(ValueError): EvidenceLineageGraph([EvidenceNode("a","o:a",("missing",))])

if __name__ == "__main__": unittest.main()
