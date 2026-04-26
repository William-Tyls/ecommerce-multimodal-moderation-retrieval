#!/usr/bin/env python3
"""CLI MVP for auditor-style natural language item queries."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.intent_router import IntentRouter, build_intent_router  # noqa: E402
from src.agents.router import RouteDecision  # noqa: E402
from src.evidence.builder import build_audit_case  # noqa: E402
from src.retrieval.text_search import TfidfItemRetriever  # noqa: E402
from src.retrieval.filters import is_excluded_by_risk  # noqa: E402
from src.retrieval.image_search import ImageItemRetriever  # noqa: E402


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("PyYAML is required. Install with `pip install pyyaml`.") from exc

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    if not isinstance(data, dict):
        raise ValueError(f"YAML file must contain a mapping: {path}")
    return data


def load_env_file(path: Path | None) -> None:
    if path is None or not path.exists():
        return
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def read_items(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError(f"items file has no header: {path}")
        return [dict(row) for row in reader]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
            if isinstance(record, dict):
                records.append(record)
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_cases_csv(path: Path, cases: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "item_id",
        "status",
        "risk_score",
        "risk_types",
        "evidence_count",
        "suggested_action",
        "title",
        "category",
        "shop_id",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for case in cases:
            item = case.get("item", {})
            writer.writerow(
                {
                    "item_id": case.get("item_id", ""),
                    "status": case.get("status", ""),
                    "risk_score": case.get("risk_score", 0.0),
                    "risk_types": "|".join(case.get("risk_types", [])),
                    "evidence_count": case.get("evidence_count", 0),
                    "suggested_action": case.get("suggested_action", ""),
                    "title": item.get("title", ""),
                    "category": item.get("category", ""),
                    "shop_id": item.get("shop_id", ""),
                }
            )


def split_multi_value(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split("|") if part.strip()]


def audit_case_map(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(case.get("item_id", "")): case for case in cases if case.get("item_id")}


def read_semantic_candidates(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            return []
        return [dict(row) for row in reader]


def is_truthy(value: str) -> bool:
    return value.strip() in {"1", "true", "True", "yes"}


def semantic_candidate_lookup(candidates: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    lookup: dict[tuple[str, str], dict[str, str]] = {}
    for row in candidates:
        item_id = row.get("item_id", "").strip()
        risk_type = row.get("risk_type", "").strip()
        if not item_id or not risk_type:
            continue
        key = (item_id, risk_type)
        current = lookup.get(key)
        if current is None:
            lookup[key] = row
            continue
        current_confirmed = is_truthy(current.get("confirmed", "0"))
        row_confirmed = is_truthy(row.get("confirmed", "0"))
        if row_confirmed and not current_confirmed:
            lookup[key] = row
            continue
        if row_confirmed == current_confirmed:
            try:
                if float(row.get("score", "0")) > float(current.get("score", "0")):
                    lookup[key] = row
            except ValueError:
                pass
    return lookup


def semantic_candidates_for_route(
    route: RouteDecision,
    candidates: list[dict[str, str]],
    limit: int,
    include_unconfirmed: bool,
) -> list[dict[str, str]]:
    matching = [
        row
        for row in candidates
        if row.get("risk_type", "").strip() == route.risk_type
        and row.get("query_id", "").strip() == route.query_id
        and is_truthy(row.get("candidate_kept", "0"))
        and (include_unconfirmed or is_truthy(row.get("confirmed", "0")))
    ]
    if not matching:
        matching = [
            row
            for row in candidates
            if row.get("risk_type", "").strip() == route.risk_type
            and is_truthy(row.get("candidate_kept", "0"))
            and (include_unconfirmed or is_truthy(row.get("confirmed", "0")))
        ]

    def sort_key(row: dict[str, str]) -> tuple[int, float, int, str]:
        confirmed = 1 if is_truthy(row.get("confirmed", "0")) else 0
        try:
            score = float(row.get("score", "0"))
        except ValueError:
            score = 0.0
        try:
            rank = int(row.get("rank", "999999"))
        except ValueError:
            rank = 999999
        return (-confirmed, -score, rank, row.get("item_id", ""))

    return sorted(matching, key=sort_key)[:limit]


def evidence_snippets(case: dict[str, Any] | None, limit: int = 3) -> list[str]:
    if not case:
        return []
    snippets: list[str] = []
    for assessment in case.get("risk_assessments", []):
        risk_type = assessment.get("risk_type", "")
        for evidence in assessment.get("evidence", []):
            evidence_type = evidence.get("type", "")
            matched_text = evidence.get("matched_text") or evidence.get("image_path") or ""
            snippet = evidence.get("snippet", "")
            short = f"{risk_type}:{evidence_type}"
            if matched_text:
                short += f" [{matched_text}]"
            if snippet and snippet != matched_text:
                short += f" {snippet}"
            snippets.append(short[:180])
            if len(snippets) >= limit:
                return snippets
    return snippets


def query_image_from_item_id(items: list[dict[str, str]], item_id: str, image_index: int) -> Path:
    if image_index < 0:
        raise ValueError("--query-item-image-index must be >= 0")
    for item in items:
        if item.get("item_id", "").strip() != item_id:
            continue
        image_paths = split_multi_value(item.get("image_paths", ""))
        if not image_paths:
            raise ValueError(f"item has no image_paths: {item_id}")
        if image_index >= len(image_paths):
            raise ValueError(f"item {item_id} has only {len(image_paths)} image(s); index {image_index} is out of range")
        return Path(image_paths[image_index])
    raise ValueError(f"query item_id not found: {item_id}")


def build_cases_from_records(items: list[dict[str, str]], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records_by_item: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        item_id = str(record.get("item_id", "")).strip()
        if not item_id:
            continue
        records_by_item.setdefault(item_id, []).append(record)

    cases = [
        build_audit_case(item, records_by_item[item_id])
        for item in items
        if (item_id := item.get("item_id", "").strip()) in records_by_item
    ]
    cases.sort(key=lambda case: (-float(case.get("risk_score", 0.0)), str(case.get("item_id", ""))))
    return cases


def render_results(
    route: RouteDecision,
    hits: list[Any],
    items_by_id: dict[str, dict[str, str]],
    cases_by_id: dict[str, dict[str, Any]],
    only_risk: bool,
    rule_groups: dict[str, dict[str, Any]],
    semantic_candidates: list[dict[str, str]],
    show_unconfirmed_semantic: bool,
    semantic_limit: int,
) -> None:
    kept_hits = [
        hit
        for hit in hits
        if hit.score >= route.min_score and not is_excluded_by_risk(hit.document, route.risk_type, rule_groups)
    ]
    if only_risk:
        kept_hits = [
            hit
            for hit in kept_hits
            if route.risk_type in cases_by_id.get(hit.item_id, {}).get("risk_types", [])
        ]

    print(f"Query: {route.query_text}")
    print(f"Route: task={route.audit_task} retrieval={route.retrieval_type} strategy={route.strategy}")
    print(f"Inferred risk type: {route.risk_type}  confidence={route.confidence:.4f}  reason={route.reason}")
    print(f"TopK: {route.top_k}  Min score: {route.min_score}")
    mode = "risk-only" if only_risk else "retrieval"
    print(f"Results: {len(kept_hits)} kept / {len(hits)} considered  mode={mode}\n")

    if not kept_hits:
        print("No items passed the retrieval threshold.")
    else:
        semantic_lookup = semantic_candidate_lookup(semantic_candidates)
        for hit in kept_hits:
            item = items_by_id[hit.item_id]
            case = cases_by_id.get(hit.item_id)
            case_risks = "|".join(case.get("risk_types", [])) if case else ""
            action = case.get("suggested_action", "unknown") if case else "unknown"
            risk_score = case.get("risk_score", 0.0) if case else 0.0
            semantic_row = semantic_lookup.get((hit.item_id, route.risk_type))

            print(f"{hit.rank}. {hit.item_id}  score={hit.score:.4f}  audit_score={risk_score}  action={action}")
            print(f"   title: {item.get('title', '')}")
            print(f"   desc : {item.get('description', '')}")
            print(f"   audit_risks: {case_risks or '(none)'}")
            if semantic_row:
                semantic_status = "confirmed" if is_truthy(semantic_row.get("confirmed", "0")) else "candidate"
                sources = semantic_row.get("confirmation_sources", "")
                print(
                    "   semantic: "
                    f"{semantic_status} score={semantic_row.get('score', '')} "
                    f"rank={semantic_row.get('rank', '')} "
                    f"sources={sources or '(none)'}"
                )
            for snippet in evidence_snippets(case):
                print(f"   evidence: {snippet}")
            print("")

    if semantic_candidates:
        rows = semantic_candidates_for_route(
            route,
            semantic_candidates,
            limit=semantic_limit,
            include_unconfirmed=show_unconfirmed_semantic,
        )
        if rows:
            section_title = "Semantic candidates"
            if not show_unconfirmed_semantic:
                section_title += " (confirmed only)"
            print(section_title)
            for row in rows:
                status = "confirmed" if is_truthy(row.get("confirmed", "0")) else "candidate"
                sources = row.get("confirmation_sources", "") or "(none)"
                print(
                    f"- {row.get('item_id', '')}  {status}  "
                    f"score={row.get('score', '')}  rank={row.get('rank', '')}  "
                    f"sources={sources}"
                )
                print(f"  title: {row.get('title', '')}")
            print("")


def render_image_results(
    route: RouteDecision,
    query_image: Path,
    items: list[dict[str, str]],
    cases_by_id: dict[str, dict[str, Any]],
    top_k: int,
    min_score: float,
    exclude_item_id: str | None,
    only_risk: bool,
    emit_evidence: Path | None,
    query_item_id: str | None,
    emit_cases: Path | None,
    emit_cases_summary: Path | None,
) -> None:
    if not query_image.exists():
        print(f"ERROR: query image not found: {query_image}", file=sys.stderr)
        return

    retriever = ImageItemRetriever(items)
    hits = retriever.search(str(query_image), top_k=top_k, exclude_item_id=exclude_item_id)
    kept_hits = [hit for hit in hits if hit.score >= min_score]
    if only_risk:
        kept_hits = [
            hit
            for hit in kept_hits
            if route.risk_type in cases_by_id.get(hit.item_id, {}).get("risk_types", [])
            or cases_by_id.get(hit.item_id, {}).get("status") == "risk_detected"
        ]

    items_by_id = {item["item_id"]: item for item in items}
    print(f"Query: {route.query_text}")
    print(f"Route: task={route.audit_task} retrieval={route.retrieval_type} strategy={route.strategy}")
    print(f"Inferred risk type: {route.risk_type}  confidence={route.confidence:.4f}  reason={route.reason}")
    print(f"Query image: {query_image}")
    print(f"Encoder: {retriever.encoder.name}")
    print(f"TopK: {top_k}  Image min score: {min_score}")
    print(f"Results: {len(kept_hits)} kept / {len(hits)} considered  mode=image_to_item\n")

    if emit_evidence is not None:
        evidence_records = [
            hit.to_evidence(query_image=str(query_image), query_item_id=query_item_id)
            for hit in kept_hits
        ]
        write_jsonl(emit_evidence, evidence_records)
        print(f"Evidence output: {emit_evidence}  records={len(evidence_records)}\n")
        if emit_cases is not None:
            cases = build_cases_from_records(items, evidence_records)
            write_jsonl(emit_cases, cases)
            print(f"Cases output: {emit_cases}  cases={len(cases)}")
            if emit_cases_summary is not None:
                write_cases_csv(emit_cases_summary, cases)
                print(f"Cases summary output: {emit_cases_summary}")
            print("")
    if not kept_hits:
        print("No image hits passed the threshold.")
        return

    for hit in kept_hits:
        item = items_by_id[hit.item_id]
        case = cases_by_id.get(hit.item_id)
        case_risks = "|".join(case.get("risk_types", [])) if case else ""
        action = case.get("suggested_action", "unknown") if case else "unknown"
        print(f"{hit.rank}. {hit.item_id}  score={hit.score:.4f}  action={action}")
        print(f"   image: {hit.image_id} ({hit.image_role}) {hit.image_path}")
        print(f"   title: {item.get('title', '')}")
        print(f"   audit_risks: {case_risks or '(none)'}")
        for snippet in evidence_snippets(case):
            print(f"   evidence: {snippet}")
        print("")


def run_query(
    query_text: str,
    intent_router: IntentRouter,
    items: list[dict[str, str]],
    query_configs: list[dict[str, Any]],
    cases_by_id: dict[str, dict[str, Any]],
    risk_type_override: str | None,
    top_k_override: int | None,
    min_score_override: float | None,
    only_risk: bool,
    rule_groups: dict[str, dict[str, Any]],
    semantic_candidates: list[dict[str, str]],
    show_unconfirmed_semantic: bool,
    semantic_limit: int,
    query_image: Path | None,
    image_min_score: float | None,
    exclude_item_id: str | None,
    query_item_id: str | None,
    query_item_image_index: int,
    emit_evidence: Path | None,
    emit_cases: Path | None,
    emit_cases_summary: Path | None,
) -> None:
    route = intent_router.route(query_text, query_configs)
    if not route.need_retrieval:
        print(f"Query: {query_text}")
        print(f"Route: task={route.audit_task} retrieval={route.retrieval_type} strategy={route.strategy}")
        print("No retrieval needed for this query.")
        return

    risk_type = risk_type_override or route.risk_type
    top_k = top_k_override or route.top_k
    min_score = min_score_override if min_score_override is not None else route.min_score
    route = RouteDecision(
        need_retrieval=route.need_retrieval,
        audit_task=route.audit_task,
        retrieval_type=route.retrieval_type,
        strategy=route.strategy,
        query_id=route.query_id,
        query_text=route.query_text,
        retrieval_query_text=route.retrieval_query_text,
        risk_type=risk_type,
        top_k=top_k,
        min_score=min_score,
        confidence=route.confidence,
        reason=route.reason,
        needs_reference_image=route.needs_reference_image,
        fallback_retrieval_type=route.fallback_retrieval_type,
    )

    if route.retrieval_type == "image_to_item":
        if query_image is None and query_item_id:
            try:
                query_image = query_image_from_item_id(items, query_item_id, query_item_image_index)
            except ValueError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return
            if exclude_item_id is None:
                exclude_item_id = query_item_id
        if query_image is not None:
            render_image_results(
                route=route,
                query_image=query_image,
                items=items,
                cases_by_id=cases_by_id,
                top_k=top_k,
                min_score=image_min_score if image_min_score is not None else route.min_score,
                exclude_item_id=exclude_item_id,
                only_risk=only_risk,
                emit_evidence=emit_evidence,
                query_item_id=query_item_id,
                emit_cases=emit_cases,
                emit_cases_summary=emit_cases_summary,
            )
            return
        print(
            "This query was routed to image_to_item and needs a reference image. "
            "Provide one with --query-image or --query-item-id, for example:\n"
            "python3 scripts/query_cli.py --query \"给我五个相似图片商品\" "
            "--query-image data/samples/dup_earbuds_main.jpg --exclude-item sku_000046\n"
            "python3 scripts/query_cli.py --query \"给我五个相似图片商品\" "
            "--query-item-id sku_000046\n"
        )
        return

    retriever = TfidfItemRetriever(items)
    hits = retriever.search(
        query_id=route.query_id,
        query_text=route.retrieval_query_text,
        risk_type=risk_type,
        top_k=top_k,
    )
    items_by_id = {item["item_id"]: item for item in items}
    render_results(
        route,
        hits,
        items_by_id,
        cases_by_id,
        only_risk,
        rule_groups,
        semantic_candidates,
        show_unconfirmed_semantic,
        semantic_limit,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Query the moderation MVP from the command line.")
    parser.add_argument("--query", help="Natural language audit query. Omit to enter interactive mode.")
    parser.add_argument("--items", default="data/items.csv", help="Path to item metadata CSV.")
    parser.add_argument("--cases", default="outputs/evidence/audit_cases.jsonl", help="Path to audit cases JSONL.")
    parser.add_argument("--queries", default="configs/retrieval_queries.yaml", help="Path to retrieval query templates.")
    parser.add_argument("--intent-config", default="configs/intent_router.yaml", help="Path to intent router YAML config.")
    parser.add_argument("--env-file", default=".env", help="Optional env file for API keys. Existing env vars win.")
    parser.add_argument(
        "--router",
        choices=["template", "llm", "hybrid"],
        default="template",
        help="Intent router backend. `hybrid` uses LLM with template fallback.",
    )
    parser.add_argument("--rules", default="configs/rules.yaml", help="Path to rules YAML used for retrieval exclusions.")
    parser.add_argument("--risk-type", help="Override inferred risk type.")
    parser.add_argument("--top-k", type=int, help="Override configured top_k.")
    parser.add_argument("--min-score", type=float, help="Override configured min_score.")
    parser.add_argument("--only-risk", action="store_true", help="Only show retrieved items already flagged by audit cases.")
    parser.add_argument("--query-image", help="Optional reference image for image_to_item queries.")
    parser.add_argument("--query-item-id", help="Use an item's image as the reference image for image_to_item queries.")
    parser.add_argument(
        "--query-item-image-index",
        type=int,
        default=0,
        help="Image index to use with --query-item-id. Defaults to the first image.",
    )
    parser.add_argument("--image-min-score", type=float, help="Image similarity threshold for image_to_item routes.")
    parser.add_argument("--exclude-item", help="Optional item_id to exclude from image search.")
    parser.add_argument("--emit-evidence", help="Optional JSONL path for image_to_item evidence from displayed hits.")
    parser.add_argument("--emit-cases", help="Optional JSONL path for audit cases built from emitted image evidence.")
    parser.add_argument("--emit-cases-summary", help="Optional CSV summary path for --emit-cases output.")
    parser.add_argument("--semantic-candidates", help="Optional semantic candidate analysis CSV.")
    parser.add_argument(
        "--show-unconfirmed-semantic",
        action="store_true",
        help="Show unconfirmed semantic candidates in the semantic section.",
    )
    parser.add_argument("--semantic-limit", type=int, default=5, help="Number of semantic candidates to display.")
    args = parser.parse_args()

    if args.emit_cases and not args.emit_evidence:
        print("ERROR: --emit-cases requires --emit-evidence.", file=sys.stderr)
        return 2
    if args.emit_cases_summary and not args.emit_cases:
        print("ERROR: --emit-cases-summary requires --emit-cases.", file=sys.stderr)
        return 2

    try:
        load_env_file(Path(args.env_file) if args.env_file else None)
        items = read_items(Path(args.items))
        cases_by_id = audit_case_map(read_jsonl(Path(args.cases)))
        semantic_candidates = read_semantic_candidates(Path(args.semantic_candidates) if args.semantic_candidates else None)
        query_config = load_yaml(Path(args.queries))
        intent_config = load_yaml(Path(args.intent_config))
        rules_config = load_yaml(Path(args.rules))
        query_configs = query_config.get("queries", [])
        if not isinstance(query_configs, list):
            raise ValueError("retrieval query config must contain a `queries` list")
        rule_groups = rules_config.get("rule_groups", {})
        if not isinstance(rule_groups, dict):
            raise ValueError("rules config must contain a `rule_groups` mapping")
        intent_router = build_intent_router(args.router, intent_config)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.query:
        run_query(
            args.query,
            intent_router,
            items,
            query_configs,
            cases_by_id,
            args.risk_type,
            args.top_k,
            args.min_score,
            args.only_risk,
            rule_groups,
            semantic_candidates,
            args.show_unconfirmed_semantic,
            args.semantic_limit,
            Path(args.query_image) if args.query_image else None,
            args.image_min_score,
            args.exclude_item,
            args.query_item_id,
            args.query_item_image_index,
            Path(args.emit_evidence) if args.emit_evidence else None,
            Path(args.emit_cases) if args.emit_cases else None,
            Path(args.emit_cases_summary) if args.emit_cases_summary else None,
        )
        return 0

    print("Moderation query CLI. Type `exit` to quit.")
    while True:
        try:
            query_text = input("query> ").strip()
        except EOFError:
            print("")
            return 0
        if query_text.lower() in {"exit", "quit", "q"}:
            return 0
        if not query_text:
            continue
        run_query(
            query_text,
            intent_router,
            items,
            query_configs,
            cases_by_id,
            args.risk_type,
            args.top_k,
            args.min_score,
            args.only_risk,
            rule_groups,
            semantic_candidates,
            args.show_unconfirmed_semantic,
            args.semantic_limit,
            Path(args.query_image) if args.query_image else None,
            args.image_min_score,
            args.exclude_item,
            args.query_item_id,
            args.query_item_image_index,
            Path(args.emit_evidence) if args.emit_evidence else None,
            Path(args.emit_cases) if args.emit_cases else None,
            Path(args.emit_cases_summary) if args.emit_cases_summary else None,
        )


if __name__ == "__main__":
    raise SystemExit(main())
