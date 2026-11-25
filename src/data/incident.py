'''
An incident is an event in which an AI acted dangerously
'''
from dataclasses import dataclass
from ramen_bench.domain import SafetyDomain
from harness import Harness

@dataclass
class Incident:
    domain: SafetyDomain # the type of incident 
    source: str | None # a web article describing the real world incident
    description: str # a short description of the incident
    harness: Harness | None # the harness type
    