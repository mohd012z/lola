import unittest

import prospective_repair_authorization_binding_legacy as _legacy
from prospective_execution_fixture_adapter import upgrade_payload

# Preserve the original helper class for the execution-receipt contract tests.
# This module's own test suite is migrated through load_tests below rather than
# mutating the legacy class globally.
_digest = _legacy._digest
ProspectiveRepairAuthorizationBindingTests = (
    _legacy.ProspectiveRepairAuthorizationBindingTests
)


class _MigratedProspectiveRepairAuthorizationBindingTests(
    _legacy.ProspectiveRepairAuthorizationBindingTests
):
    def _payload(self):
        return upgrade_payload(super()._payload())


def load_tests(loader, tests, pattern):
    return loader.loadTestsFromTestCase(
        _MigratedProspectiveRepairAuthorizationBindingTests
    )
