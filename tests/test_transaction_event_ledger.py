import unittest
from lola_transaction_event_ledger import TransactionEventLedger

class TransactionEventLedgerTests(unittest.TestCase):
    def test_same_idempotency_key_is_not_started_twice(self):
        ledger=TransactionEventLedger()
        a=ledger.begin("tx1","episode:e1|knowledge:k1|fp:abc")
        b=a.ledger.begin("tx2","episode:e1|knowledge:k1|fp:abc")
        self.assertEqual(a.status,"STARTED")
        self.assertEqual(b.status,"DUPLICATE")
        self.assertEqual(b.existing_transaction_id,"tx1")

    def test_completed_transaction_replays_terminal_result(self):
        ledger=TransactionEventLedger()
        started=ledger.begin("tx1","key1")
        completed=started.ledger.complete("tx1","VERIFIED_COMMIT",{"version":2})
        replay=completed.ledger.begin("tx2","key1")
        self.assertEqual(replay.status,"REPLAY")
        self.assertEqual(replay.terminal_status,"VERIFIED_COMMIT")
        self.assertEqual(replay.result,{"version":2})

    def test_incomplete_transaction_is_resumable(self):
        ledger=TransactionEventLedger().begin("tx1","key1").ledger
        r=ledger.resume("tx1")
        self.assertEqual(r.status,"RESUME")
        self.assertEqual(r.last_event,"BEGIN")
        self.assertFalse(r.execution_authority)

if __name__ == "__main__": unittest.main()
