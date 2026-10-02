import prospective_result_lock_binding_legacy as _legacy
from prospective_execution_fixture_adapter import upgrade_payload

_original_payload = _legacy.ProspectiveResultSelectionLockBindingTests._payload


def _payload(self):
    return upgrade_payload(_original_payload(self))


_legacy.ProspectiveResultSelectionLockBindingTests._payload = _payload
ProspectiveResultSelectionLockBindingTests = (
    _legacy.ProspectiveResultSelectionLockBindingTests
)
