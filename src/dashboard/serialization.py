#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JSON serialization helpers for dashboard DTOs."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel


def to_jsonable(model: BaseModel) -> dict:
    """Return a JSON-serializable dict (Decimals as strings, datetimes ISO-8601)."""
    return model.model_dump(mode="json")


def to_json(model: BaseModel) -> str:
    """Return a compact JSON string suitable for a React client."""
    return model.model_dump_json()


def parse_json(payload: str) -> Any:
    """Parse JSON text; used by tests to prove the payload is standard JSON."""
    return json.loads(payload)
