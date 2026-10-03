import unittest

from lola_security_contracts import (
    ActionRequest,
    ArtifactContext,
    Capability,
    ContractActionClass,
    SecurityFinding,
    Taint,
    content_digest,
)


class SecurityContractTests(unittest.TestCase):
    def test_artifact_identity_and_hash_are_deterministic(self):
        artifact = ArtifactContext.from_payload(
            artifact_id="a1",
            project_id="p1",
            source_type="APK_RESOURCE",
            source_id="classes.dex",
            payload="hello",
            taints=frozenset({Taint.UNTRUSTED}),
        )
        self.assertEqual(artifact.content_hash, content_digest("hello"))
        self.assertEqual(artifact.artifact_id, "a1")

    def test_parent_provenance_and_taint_are_inherited(self):
        parent = ArtifactContext.from_payload(
            artifact_id="apk",
            project_id="p1",
            source_type="APK",
            source_id="sample.apk",
            payload="root",
            taints=frozenset({Taint.UNTRUSTED}),
        )
        child = ArtifactContext.from_payload(
            artifact_id="dex",
            project_id="p1",
            source_type="DEX",
            source_id="classes.dex",
            payload="derived",
            parent=parent,
            transformation="extract-dex",
        )
        self.assertEqual(child.parent_artifact_id, "apk")
        self.assertEqual(child.parent_content_hash, parent.content_hash)
        self.assertIn(Taint.UNTRUSTED, child.taints)
        self.assertIn(Taint.DERIVED_FROM_UNTRUSTED, child.taints)
        self.assertEqual(child.transformation_chain, ("extract-dex",))

    def test_capability_enumeration_and_action_request(self):
        request = ActionRequest(
            name="save-report",
            action_class=ContractActionClass.SIDE_EFFECT,
            requested_capabilities=frozenset({Capability.WRITE_LOCAL_REPORT}),
            target="report.json",
            trace_id="trace-1",
        )
        self.assertTrue(request.requires(Capability.WRITE_LOCAL_REPORT))
        self.assertFalse(request.requires(Capability.EXTERNAL_ACTION))

    def test_security_finding_preserves_evidence(self):
        finding = SecurityFinding(
            detector_id="prompt-injection",
            detector_version="1",
            category="ROLE_OVERRIDE",
            artifact_id="dex",
            evidence_refs=("e1",),
            confidence=0.9,
            features=("role-override",),
        )
        self.assertEqual(finding.evidence_refs, ("e1",))
        self.assertEqual(finding.artifact_id, "dex")


if __name__ == "__main__":
    unittest.main()
