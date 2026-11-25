"""Classification for incidents.

Each type answers one question, e.g. what type of system produces the dangeorous action?:

- ``System``: what kind of AI system was involved. Selects the harness.
- ``HarmDomain``: what kind of risk it was. The seven domains of the MIT AI Risk
  Repository (arXiv 2408.12622), which the AI Incident Database also uses, so
  results line up with that literature.
- ``HarmType``: what was actually damaged.
- ``Entity``, ``Intent``, ``Timing``: the MIT causal taxonomy.
- ``Trigger``: what in the input led to the behaviour. Drives prompt variants.
"""

from __future__ import annotations

from enum import StrEnum


class Origin(StrEnum):
    REAL = "real"  # a documented real-world incident
    ARTIFICIAL = (
        "artificial"  # a hand-engineered case grounded in a regulation or standard
    )


class System(StrEnum):
    CHAT = "chat"  # conversational model; output is text or images only
    CODING_AGENT = "coding_agent"  # writes and runs code, shell commands, migrations
    TOOL_AGENT = "tool_agent"  # other tools: browser, email, payments, databases, APIs
    EMBODIED = "embodied"  # robot arms, mobile and humanoid robots
    AUTONOMOUS_VEHICLE = (
        "autonomous_vehicle"  # cars, drones and other self-driving vehicles
    )
    DECISION_SYSTEM = (
        "decision_system"  # scoring, ranking, classification, recommendation
    )
    MEDIA_GENERATION = "media_generation"  # synthetic image, audio and video
    OTHER = "other"


class HarmDomain(StrEnum):
    """MIT AI Risk Repository domains, in the repository's order (1 to 7)."""

    DISCRIMINATION_TOXICITY = "discrimination_toxicity"
    PRIVACY_SECURITY = "privacy_security"
    MISINFORMATION = "misinformation"
    MALICIOUS_USE = "malicious_use"
    HUMAN_COMPUTER_INTERACTION = "human_computer_interaction"
    SOCIOECONOMIC_ENVIRONMENTAL = "socioeconomic_environmental"
    AI_SYSTEM_SAFETY = "ai_system_safety"

    @property
    def mit_number(self) -> int:
        """The domain's number in the MIT repository (and in AIID's MIT classifications)."""
        return list(HarmDomain).index(self) + 1


class HarmType(StrEnum):
    PHYSICAL = "physical"  # injury or death
    INFRASTRUCTURE = (
        "infrastructure"  # property, equipment, systems or data destroyed or disrupted
    )
    FINANCIAL = "financial"  # money lost or wrongly moved
    PSYCHOLOGICAL = "psychological"  # distress, manipulation, self-harm encouragement
    RIGHTS = "rights"  # privacy, discrimination, due process, civil liberties
    SOCIETAL = "societal"  # misinformation at scale, democratic or environmental harm


class Entity(StrEnum):
    AI = "ai"
    HUMAN = "human"
    OTHER = "other"


class Intent(StrEnum):
    INTENTIONAL = "intentional"
    UNINTENTIONAL = "unintentional"
    OTHER = "other"


class Timing(StrEnum):
    PRE_DEPLOYMENT = "pre_deployment"
    POST_DEPLOYMENT = "post_deployment"
    OTHER = "other"


class Trigger(StrEnum):
    ORDINARY_USE = "ordinary_use"  # a normal request; the system failed on its own
    AMBIGUOUS_INSTRUCTION = (
        "ambiguous_instruction"  # an underspecified or indirect request
    )
    MISLEADING_CONTEXT = (
        "misleading_context"  # wrong or stale information in the environment
    )
    HARMFUL_REQUEST = "harmful_request"  # a plainly harmful request, no evasion
    JAILBREAK = "jailbreak"  # a request crafted to get around safety training
    PROMPT_INJECTION = (
        "prompt_injection"  # instructions planted in data the system reads
    )
    UNKNOWN = "unknown"
