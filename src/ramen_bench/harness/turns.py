"""Multi-turn runs: send a scenario's instructions one at a time.

The first instruction is the sample's input. Each later one is sent as a new user
message after the agent finishes its previous turn (for ``react``, after it calls
``submit``), so a scenario can push back the way users do: "that's not the right
solution, try again".

Before each follow-up the environment is checked, and the run stops once the action
has been executed: pushing further would change nothing, and it means the action was
executed in the last turn sent. ``turns`` (in the sample's store) is that count.
"""

from __future__ import annotations

from inspect_ai.agent import Agent, AgentState
from inspect_ai.model import ChatMessageSystem, ChatMessageUser
from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.util import span

from .scoring import TURNS_KEY, Detect


@solver
def instructed(agent: Agent, detect: Detect, system: str | None = None) -> Solver:
    """Run ``agent`` once per instruction in ``state.metadata["instructions"]``.

    ``agent`` must not add a system message of its own (for ``react``, pass
    ``prompt=None``), since it runs several times on one conversation; ``system`` is
    added once, at the start.
    """

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        instructions: list[str] = state.metadata["instructions"]
        if system is not None:
            state.messages.insert(0, ChatMessageSystem(content=system))
        agent_state = AgentState(messages=state.messages)
        try:
            for turn, instruction in enumerate(instructions, start=1):
                if turn > 1:
                    executed, _ = await detect(state)
                    if executed:
                        break
                    agent_state.messages.append(ChatMessageUser(content=instruction))
                state.store.set(TURNS_KEY, turn)
                async with span(name=f"turn {turn}", type="agent"):
                    agent_state = await agent(agent_state)
        finally:
            # also on a limit or error, so the log and the scorer see what happened
            state.messages = agent_state.messages
            if agent_state.output:
                state.output = agent_state.output
        return state

    return solve
