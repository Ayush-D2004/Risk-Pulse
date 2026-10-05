import re
from typing import Tuple

STRONG_TERMS = [
    r"\bdefault(?:s|ed)?\b", 
    r"\bbankrupt(?:cy)?\b", 
    r"\binsolven(?:cy|t)\b", 
    r"\bdebt restructuring\b", 
    r"\bmissed payment\b", 
    r"\bcovenant breach\b", 
    r"\b(?:credit|rating) downgrade\b", 
    r"\bdebt distress\b", 
    r"\bbond default\b", 
    r"\bloan default\b"
]

WEAK_CONTEXTS = [
    r"\bdefault (?:browser|setting|password|option|app|theme)\b",
    r"\bdefault(?:ly)?\b"
]

def check_credit_event_guard(
    text: str,
    candidate_entity: str,
    canonical_entity: str,
    entity_status: str
) -> Tuple[bool, str]:
    """
    Evaluates a candidate Credit Event signal to determine if it survives deterministic 
    lexical and entity collision checks.
    
    Returns:
        (passed_guard: bool, guard_reason: str)
    """
    text_lower = str(text).lower()
    cand_lower = str(candidate_entity).lower()
    
    # 1. Lexical Collisions (must be checked specifically around 'default')
    # If a weak context is present, and no strong context overrides it (actually, for safety, if weak context is present, we might reject, 
    # but let's just reject if it matches weak context specifically as the *only* reason for 'default').
    # But for simplicity, if a known weak context like 'default browser' appears, we can reject it if it's a lexical collision.
    for wc in WEAK_CONTEXTS:
        if re.search(wc, text_lower):
            return False, "LEXICAL_COLLISION"
            
    # 2. Entity Collisions
    # If the entity is unresolved_source, reject
    if entity_status == "unresolved_source":
        return False, "ENTITY_COLLISION_PUBLISHER"
        
    # Check specific person/concept collisions
    if cand_lower == "ford" and any(name in text_lower for name in ["christine ", "rob ", "doug ", "tom "]):
        return False, "ENTITY_COLLISION_PERSON"
        
    if cand_lower == "disney" and "walt disney" in text_lower:
        return False, "ENTITY_COLLISION_PERSON"
        
    if cand_lower == "visa" and any(v in text_lower for v in ["f-1", "f1", "h1b", "h-1b", "tourist", "travel"]):
        return False, "ENTITY_COLLISION_CONCEPT"
        
    # 3. Strong Credit Evidence
    has_strong = False
    for st in STRONG_TERMS:
        if re.search(st, text_lower):
            has_strong = True
            break
            
    if not has_strong:
        # We need strong evidence for a Credit Event. If none found, it's either an ambiguous or non-credit financial event.
        return False, "MISSING_STRONG_CREDIT_EVIDENCE"
        
    return True, "PASSED"
