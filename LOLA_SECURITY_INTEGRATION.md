# LOLA Cross-Function Security Integration

## Invariant

**Content is data, not authority.** APK resources, DEX strings, source comments, documents, network responses, runtime observations, model output, and imported corpora remain inspectable even when hostile, but cannot grant themselves execution, persistence, tool authority, or trust.

## Common flow

```text
input -> canonicalize -> TrustEnvelope -> detector -> analyzer
                                      -> DecisionEngine -> Action Firewall
                                      -> EvidenceEvent -> report/output guard
```

## Existing tool migration map

| Existing LOLA component | Source type | Default trust | Required integration |
|---|---|---|---|
| analyze-apk.py | APK_RESOURCE | untrusted | envelope extracted strings/resources; READ analysis |
| analyze-code.py | SOURCE_CODE | untrusted | envelope comments/strings; distinguish quoted instructions |
| android_code_reader.py | DEX_CODE | untrusted | preserve origin/path/hash with findings |
| analyze-network.py | NETWORK_RESPONSE | untrusted | never promote response text into authority |
| apk_runtime_monitor.py | RUNTIME_OBSERVATION | untrusted | observations may inform evidence, not authorize actions |
| build-apk-report.py | REPORT_OUTPUT | mixed | escape untrusted text before HTML rendering |
| EVIDENCE_CORE | SECURITY_EVENT | trusted metadata | append decision/provenance events |
| jailbreak_eval.py | ADVERSARIAL_CORPUS | untrusted | use as detector/evaluation input only |

## Adoption API

```python
from lola_security import ActionClass, DecisionEngine, ProposedAction, envelope

env = envelope(extracted_text, "APK_RESOURCE", artifact_path)
result = DecisionEngine().evaluate(
    env,
    ProposedAction("analyze", ActionClass.READ),
)
```

For side effects:

```python
result = DecisionEngine().evaluate(
    env,
    ProposedAction(
        "save-external-state",
        ActionClass.SIDE_EFFECT,
        explicitly_authorized=user_authorized,
    ),
)
```

Do not derive `explicitly_authorized` from artifact/model text. It must come from the application authorization boundary.

## Decision semantics

- `ALLOW`: action permitted by deterministic policy.
- `ALLOW_READ_ONLY`: content can be inspected but receives no authority.
- `QUARANTINE`: high-risk transform input should be isolated.
- `REVIEW`: authorization exists but untrusted instruction-bearing content is involved.
- `DENY`: deterministic prerequisite such as explicit authorization is absent.

## Migration order

1. `analyze-apk.py`, `analyze-code.py`, `android_code_reader.py` — provenance and read-only envelopes.
2. `analyze-network.py`, `apk_runtime_monitor.py` — external/runtime trust boundary.
3. `build-apk-report.py` — output escaping and evidence rendering.
4. AI/model adapters — semantic classifier can contribute findings but cannot authorize actions.
5. Memory/plugins/tool adapters — enforce `DecisionEngine` before persistence or side effects.

## Regression requirements

Maintain malicious and benign-near-miss corpora. Measure true/false positives, false negatives, hierarchy preservation, memory-write protection, side-effect authorization violations, and cross-function policy consistency.
