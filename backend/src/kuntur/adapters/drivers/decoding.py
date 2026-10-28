"""Shared rules for turning a device's answer into a reading."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from kuntur.domain.readings import FailureCause, Reading


def sentence(text: str) -> str:
    """Upper-cases the first letter only (``str.capitalize`` would lower-case "UPS")."""
    return text[:1].upper() + text[1:]


def assemble(
    device_id: str, at: datetime, metrics: Mapping[str, float], problems: Sequence[str], *, empty_detail: str
) -> Reading:
    """Every value that cannot be right was left out and named in ``problems``. Some values missing is a
    PARTIAL reading (yellow, never a silent green); none at all is a FAILED one."""
    if not metrics:
        return Reading.failed(device_id, at, FailureCause.INVALID_DATA, empty_detail)
    if problems:
        return Reading.partial(
            device_id, at, metrics, FailureCause.INVALID_DATA, sentence("; ".join(problems))
        )
    return Reading.ok(device_id, at, metrics)
