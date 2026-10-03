import unittest
from lola_transfer_governance import govern_transfer_routing

class TransferGovernanceTests(unittest.TestCase):
    def test_transfer_evidence_is_required(self):
        r=govern_transfer_routing(["e1","e2"],["o1","o2"],[],{"domain":"build"},transfer_supported=False)
        self.assertFalse(r.promotable)
        self.assertEqual(r.reason,"transfer_not_supported")

    def test_supported_transfer_can_pass_but_never_authorizes_execution(self):
        r=govern_transfer_routing(["e1","e2"],["o1","o2"],[],{"domain":"build"},transfer_supported=True)
        self.assertTrue(r.promotable)
        self.assertFalse(r.execution_authority)

if __name__ == "__main__": unittest.main()
