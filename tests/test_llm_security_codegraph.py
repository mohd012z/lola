import hashlib

import pytest

from llm_security.codegraph import CodeEdge, CodeGraph, CodeNode, OffsetRef, sha256_bytes, source_ref


def test_source_ref_tracks_exact_bytes_and_lines():
    data = b"alpha\nbeta\n"
    ref = source_ref("sample.py", data)
    assert ref.source_sha256 == hashlib.sha256(data).hexdigest()
    assert ref.byte_start == 0
    assert ref.byte_end == len(data)
    assert ref.line_start == 1
    assert ref.line_end == 3


def test_sha_changes_when_source_mutates():
    before = b"value = 1\n"
    after = b"value = 2\n"
    assert sha256_bytes(before) != sha256_bytes(after)


def test_empty_source_has_zero_line_range():
    ref = source_ref("empty.py", b"")
    assert ref.byte_start == 0
    assert ref.byte_end == 0
    assert ref.line_start == 0
    assert ref.line_end == 0


def test_invalid_utf8_is_observed_without_execution():
    data = b"name = \xff\n"
    ref = source_ref("broken.py", data)
    assert ref.source_sha256 == hashlib.sha256(data).hexdigest()
    assert ref.byte_end == len(data)
    assert ref.line_start == 1


def test_graph_rejects_edge_with_missing_endpoint():
    ref = OffsetRef("sample.py", "a" * 64, 0, 1, 1, 1, "a")
    graph = CodeGraph()
    graph.add_node(CodeNode("a", "function", "a", ref))
    with pytest.raises(ValueError):
        graph.add_edge(CodeEdge("a", "missing", "CALLS"))


def test_graph_accepts_edge_after_both_nodes_exist():
    ref_a = OffsetRef("sample.py", "a" * 64, 0, 1, 1, 1, "a")
    ref_b = OffsetRef("sample.py", "a" * 64, 2, 3, 2, 2, "b")
    graph = CodeGraph()
    graph.add_node(CodeNode("a", "function", "a", ref_a))
    graph.add_node(CodeNode("b", "function", "b", ref_b))
    graph.add_edge(CodeEdge("a", "b", "CALLS"))
    assert graph.edges == [CodeEdge("a", "b", "CALLS")]
