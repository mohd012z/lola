import prospective_result_evidence_binding_legacy as _legacy
from prospective_execution_fixture_adapter import upgrade_payload

_original_payload = _legacy.ProspectiveResultEvidenceBindingTests._payload


def _payload(self):
    return upgrade_payload(_original_payload(self))


_legacy.ProspectiveResultEvidenceBindingTests._payload = _payload
ProspectiveResultEvidenceBindingTests = _legacy.ProspectiveResultEvidenceBindingTests
