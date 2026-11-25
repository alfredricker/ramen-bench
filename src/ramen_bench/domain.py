'''
Enum of the types of AI safety incidents
'''
from enum import Enum

class SafetyDomain(Enum):
    CODING = "CODING"
    PHYSICAL = "PHYSICAL"
    ETHICAL = "ETHICAL"