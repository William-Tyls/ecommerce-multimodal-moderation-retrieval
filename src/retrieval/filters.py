"""Post filters for retrieval hits."""

from __future__ import annotations

import re
from typing import Any


def is_excluded_by_risk(text: str, risk_type: str, rule_groups: dict[str, dict[str, Any]]) -> bool:
    group = rule_groups.get(risk_type, {})
    if not isinstance(group, dict):
        return False

    for keyword in group.get("exclude_keywords") or []:
        if re.search(re.escape(str(keyword)), text, flags=re.IGNORECASE):
            return True

    for pattern_text in group.get("exclude_regex") or []:
        if re.search(str(pattern_text), text, flags=re.IGNORECASE):
            return True

    return False
