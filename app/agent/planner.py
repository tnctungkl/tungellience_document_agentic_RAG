from app.agent.state import AgentState


class AgentPlanner:
    """Keep orchestration decisions explicit and easy to inspect."""

    min_generation_confidence = 0.25

    def next_action(self, state: AgentState) -> str:
        if state.action == "retrieve" and not state.results:
            return "retrieve"
        if state.results and state.confidence < self.min_generation_confidence:
            return "verify"
        return "answer"
