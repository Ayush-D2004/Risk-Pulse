import pytest
from src.risk.credit_event_guard import check_credit_event_guard

def test_genuine_positive_bankruptcy():
    passed, reason = check_credit_event_guard("Company files for bankruptcy protection", "Acme", "Acme Corp", "valid")
    assert passed is True
    assert reason == "PASSED"

def test_genuine_positive_default():
    passed, reason = check_credit_event_guard("Acme defaults on loan", "Acme", "Acme Corp", "valid")
    assert passed is True
    
def test_genuine_positive_missed_payment():
    passed, reason = check_credit_event_guard("Acme missed payment to bondholders", "Acme", "Acme Corp", "valid")
    assert passed is True

def test_genuine_positive_debt_restructuring():
    passed, reason = check_credit_event_guard("Acme announces debt restructuring", "Acme", "Acme Corp", "valid")
    assert passed is True
    
def test_genuine_positive_covenant_breach():
    passed, reason = check_credit_event_guard("Covenant breach by Acme", "Acme", "Acme Corp", "valid")
    assert passed is True
    
def test_genuine_positive_downgrade():
    passed, reason = check_credit_event_guard("Moody's announces credit downgrade for Acme", "Acme", "Acme Corp", "valid")
    assert passed is True

def test_lexical_collision_default_browser():
    passed, reason = check_credit_event_guard("How to change the default browser on Mac", "Mac", "Apple Inc.", "valid")
    assert passed is False
    assert reason == "LEXICAL_COLLISION"

def test_lexical_collision_default_settings():
    passed, reason = check_credit_event_guard("Reset to default settings", "Acme", "Acme Corp", "valid")
    assert passed is False
    assert reason == "LEXICAL_COLLISION"

def test_entity_collision_christine_ford():
    passed, reason = check_credit_event_guard("Christine Ford testifies today", "Ford", "Ford Motor Company", "valid")
    assert passed is False
    assert reason == "ENTITY_COLLISION_PERSON"

def test_entity_collision_walt_disney():
    passed, reason = check_credit_event_guard("Walt Disney was a visionary", "Disney", "Walt Disney Co", "valid")
    assert passed is False
    assert reason == "ENTITY_COLLISION_PERSON"

def test_entity_collision_f1_visa():
    passed, reason = check_credit_event_guard("Applying for an F-1 visa", "Visa", "Visa Inc", "valid")
    assert passed is False
    assert reason == "ENTITY_COLLISION_CONCEPT"

def test_unresolved_publisher_entity():
    passed, reason = check_credit_event_guard("Reuters defaults on reporting standard", "Reuters", "", "unresolved_source")
    assert passed is False
    assert reason == "ENTITY_COLLISION_PUBLISHER"

def test_missing_strong_evidence():
    passed, reason = check_credit_event_guard("Company earnings plummeted 20% today", "Acme", "Acme Corp", "valid")
    assert passed is False
    assert reason == "MISSING_STRONG_CREDIT_EVIDENCE"
