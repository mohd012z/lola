import prospective_result_gate_legacy as _legacy
from prospective_execution_fixture_adapter import upgrade_payload

_original_valid_payload = _legacy.ProspectiveResultGateTests._valid_payload


def _valid_payload(self):
    return upgrade_payload(_original_valid_payload(self))


_legacy.ProspectiveResultGateTests._valid_payload = _valid_payload
ProspectiveResultGateTests = _legacy.ProspectiveResultGateTests
