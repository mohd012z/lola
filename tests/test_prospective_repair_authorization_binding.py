import unittest

import prospective_repair_authorization_binding_legacy as _legacy
from prospective_execution_fixture_adapter import upgrade_payload

# Preserve the original helper class for the execution-receipt contract tests.
# Migrated tests subclass it below; the raw class is intentionally NOT
# re-exported at module level so pytest does not collect it directly (its
# fixtures predate the execution-receipt contract).


class _MigratedProspectiveRepairAuthorizationBindingTests(
    _legacy.ProspectiveRepairAuthorizationBindingTests
):
    def _payload(self):
        return upgrade_payload(super()._payload())


def load_tests(loader, tests, pattern):
    return loader.loadTestsFromTestCase(
        _MigratedProspectiveRepairAuthorizationBindingTests
    )
