"""Compact deterministic dispatcher for Lola episode projections."""

def engines_for_event(topic: str):
    if topic == "agent.handoff":
        return ("TASK", "AGENT")
    if topic in {"agent.failure", "agent.recovery"}:
        return ("TASK", "AGENT", "FAILURE")
    if topic == "cognitive.verification":
        return ("TASK", "AGENT", "LEARNING")
    if topic.startswith("agent."):
        return ("TASK", "AGENT")
    return ("TASK",)
