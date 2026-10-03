"""Typed relations among episode projections; no voting semantics."""
from __future__ import annotations
from dataclasses import dataclass

_ALLOWED={"PARENT_OF","CHILD_OF","PRECEDES","CAUSES","CORRELATES_WITH","CONTRADICTS","VERIFIES","SUPERSEDES","SAME_TASK","SAME_FAILURE","SAME_AGENT","SAME_ARTIFACT","TRANSFER_OF","COUNTEREXAMPLE_OF"}

@dataclass(frozen=True, order=True)
class EpisodeLink:
    source_episode_id: str
    relation: str
    target_episode_id: str
    def __post_init__(self):
        if self.relation not in _ALLOWED:
            raise ValueError("unsupported episode relation")

def join_episode_links(links):
    return tuple(sorted(set(links)))
