import prospective_repair_authorization_binding_legacy as _legacy
from prospective_execution_fixture_adapter import upgrade_payload

_original_payload = _legacy.ProspectiveRepairAuthorizationBindingTests._payload


def _payload(self):
    return upgrade_payload(_original_payload(self))


_legacy.ProspectiveRepairAuthorizationBindingTests._payload = _payload
ProspectiveRepairAuthorizationBindingTests = (
    _legacy.ProspectiveRepairAuthorizationBindingTests
)
