"""Rule-based moderation matching for item text fields."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


TEXT_FIELDS = ("title", "description", "ocr_text")


@dataclass(frozen=True)
class RuleMatch:
    item_id: str
    risk_type: str
    field: str
    match_type: str
    rule: str
    matched_text: str
    start: int
    end: int
    snippet: str
    confidence: float

    def to_evidence(self, suggested_action: str = "manual_review") -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "risk_type": self.risk_type,
            "confidence": self.confidence,
            "evidence": {
                "type": f"{self.field}_{self.match_type}_match",
                "field": self.field,
                "matched_text": self.matched_text,
                "rule": self.rule,
                "span": [self.start, self.end],
                "snippet": self.snippet,
            },
            "suggested_action": suggested_action,
        }


def split_multi_value(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split("|") if part.strip()]


def iter_text_values(item: dict[str, str], fields: Iterable[str] = TEXT_FIELDS) -> Iterable[tuple[str, str]]:
    for field in fields:
        value = item.get(field, "")
        if not value:
            continue
        if field == "ocr_text":
            for part in split_multi_value(value):
                yield field, part
        else:
            yield field, value.strip()


def make_snippet(text: str, start: int, end: int, window: int = 24) -> str:
    left = max(start - window, 0)
    right = min(end + window, len(text))
    prefix = "..." if left > 0 else ""
    suffix = "..." if right < len(text) else ""
    return f"{prefix}{text[left:right]}{suffix}"


def find_keyword_matches(text: str, keyword: str) -> Iterable[tuple[int, int, str]]:
    if not keyword:
        return
    pattern = re.compile(re.escape(keyword), flags=re.IGNORECASE)
    for match in pattern.finditer(text):
        yield match.start(), match.end(), match.group(0)


def find_regex_matches(text: str, pattern_text: str) -> Iterable[tuple[int, int, str]]:
    pattern = re.compile(pattern_text, flags=re.IGNORECASE)
    for match in pattern.finditer(text):
        yield match.start(), match.end(), match.group(0)


def is_excluded(text: str, group: dict[str, Any]) -> bool:
    for keyword in group.get("exclude_keywords") or []:
        if re.search(re.escape(str(keyword)), text, flags=re.IGNORECASE):
            return True

    for pattern_text in group.get("exclude_regex") or []:
        if re.search(str(pattern_text), text, flags=re.IGNORECASE):
            return True

    return False


def match_item(item: dict[str, str], rule_groups: dict[str, dict[str, Any]]) -> list[RuleMatch]:
    item_id = item.get("item_id", "").strip()
    matches: list[RuleMatch] = []
    seen: set[tuple[str, str, str, int, int, str]] = set()

    for field, text in iter_text_values(item):
        for risk_type, group in rule_groups.items():
            if is_excluded(text, group):
                continue

            keywords = group.get("keywords") or []
            regexes = group.get("regex") or []

            for keyword in keywords:
                for start, end, matched_text in find_keyword_matches(text, str(keyword)):
                    key = (risk_type, field, "keyword", start, end, matched_text.lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    matches.append(
                        RuleMatch(
                            item_id=item_id,
                            risk_type=risk_type,
                            field=field,
                            match_type="keyword",
                            rule=str(keyword),
                            matched_text=matched_text,
                            start=start,
                            end=end,
                            snippet=make_snippet(text, start, end),
                            confidence=1.0,
                        )
                    )

            for regex in regexes:
                regex_text = str(regex)
                for start, end, matched_text in find_regex_matches(text, regex_text):
                    key = (risk_type, field, "regex", start, end, matched_text.lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    matches.append(
                        RuleMatch(
                            item_id=item_id,
                            risk_type=risk_type,
                            field=field,
                            match_type="regex",
                            rule=regex_text,
                            matched_text=matched_text,
                            start=start,
                            end=end,
                            snippet=make_snippet(text, start, end),
                            confidence=1.0,
                        )
                    )

    return matches


def group_matches_by_item(matches: Iterable[RuleMatch]) -> dict[str, list[RuleMatch]]:
    grouped: dict[str, list[RuleMatch]] = {}
    for match in matches:
        grouped.setdefault(match.item_id, []).append(match)
    return grouped
