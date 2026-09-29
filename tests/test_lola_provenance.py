import json
import unittest

from lola_provenance import ProvenanceGraph, derive_artifact
from lola_security_contracts import ArtifactContext, Taint, content_digest


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        binary_marker = "apk-content"
        self.root = ArtifactContext.from_payload(
            artifact_id="apk-1",
            project_id="project-1",
            source_type="APK",
            source_id="sample.apk",
            payload=binary_marker,
            taints=frozenset({Taint.UNTRUSTED, Taint.EXTERNAL}),
        )
        self.assertEqual(self.root.content_hash, content_digest(binary_marker))

    def test_derive_preserves_parent_and_untrusted_taint(self):
        child = derive_artifact(
            self.root,
            "dex-content",
            "extract-dex",
            "classes.dex",
            artifact_id="dex-1",
            source_type="DEX",
        )
        self.assertEqual(child.parent_artifact_id, self.root.artifact_id)
        self.assertEqual(child.parent_content_hash, self.root.content_hash)
        self.assertIn(Taint.UNTRUSTED, child.taints)
        self.assertIn(Taint.DERIVED_FROM_UNTRUSTED, child.taints)
        self.assertIn(Taint.EXTERNAL, child.taints)

    def test_derivation_hash_is_deterministic(self):
        one = derive_artifact(self.root, {"b": 2, "a": 1}, "decode", "x", artifact_id="one")
        two = derive_artifact(self.root, {"a": 1, "b": 2}, "decode", "x", artifact_id="two")
        self.assertEqual(one.content_hash, two.content_hash)

    def test_graph_returns_root_to_leaf_lineage(self):
        graph = ProvenanceGraph()
        graph.add_root(self.root)
        child = derive_artifact(self.root, "dex", "extract-dex", "classes.dex", artifact_id="dex")
        graph.add_derived(child, "extract-dex")
        grandchild = derive_artifact(child, "text", "extract-string", "string:1", artifact_id="string")
        graph.add_derived(grandchild, "extract-string")
        self.assertEqual([x.artifact_id for x in graph.lineage("string")], ["apk-1", "dex", "string"])

    def test_graph_is_json_serializable(self):
        graph = ProvenanceGraph()
        graph.add_root(self.root)
        payload = json.loads(graph.to_json())
        self.assertEqual(payload["artifacts"]["apk-1"]["source_id"], "sample.apk")
        self.assertIn("untrusted", payload["artifacts"]["apk-1"]["taints"])

    def test_unknown_parent_is_rejected(self):
        graph = ProvenanceGraph()
        child = derive_artifact(self.root, "dex", "extract-dex", "classes.dex", artifact_id="dex")
        with self.assertRaises(ValueError):
            graph.add_derived(child, "extract-dex")


if __name__ == "__main__":
    unittest.main()
