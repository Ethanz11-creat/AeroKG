import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

NODE_TYPE_MAP = {
    "documents": "nodes_document.json",
    "structural_units": "nodes_structural_unit.json",
    "terms": "nodes_term.json",
    "definitions": "nodes_definition.json",
    "rules": "nodes_rule.json",
    "conditions": "nodes_condition.json",
    "constraints": "nodes_constraint.json",
    "references": "nodes_reference.json",
}


class KGExporter:
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(
        self,
        results: Dict[str, Any],
        stats: Dict[str, int],
        llm_stats: Dict[str, int],
        extractor_stats: Dict[str, Any],
        failed_cases: List[Dict[str, Any]],
    ) -> str:
        for key, filename in NODE_TYPE_MAP.items():
            data = results.get(key, [])
            filepath = self.output_dir / filename
            self._write_json(filepath, data)
            logger.info(f"Exported {len(data)} items to {filepath}")

        edges = results.get("edges", [])
        edges_path = self.output_dir / "edges.json"
        self._write_json(edges_path, edges)
        logger.info(f"Exported {len(edges)} edges to {edges_path}")

        report = self._build_report(stats, llm_stats, extractor_stats, results)
        report_path = self.output_dir / "extraction_report.json"
        self._write_json(report_path, report)
        logger.info(f"Exported extraction report to {report_path}")

        if failed_cases:
            failed_path = self.output_dir / "failed_cases.jsonl"
            self._write_jsonl(failed_path, failed_cases)
            logger.info(f"Exported {len(failed_cases)} failed cases to {failed_path}")

        return str(self.output_dir)

    @staticmethod
    def _write_json(filepath: Path, data: Any) -> None:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _write_jsonl(filepath: Path, data: List[Dict]) -> None:
        with open(filepath, "w", encoding="utf-8") as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def _build_report(
        self,
        stats: Dict[str, int],
        llm_stats: Dict[str, int],
        extractor_stats: Dict[str, Any],
        results: Dict[str, Any],
    ) -> Dict[str, Any]:
        node_counts = {}
        for key in NODE_TYPE_MAP:
            node_counts[key] = len(results.get(key, []))

        return {
            "generated_at": datetime.now().isoformat(),
            "input_stats": {
                "total_chunks": stats.get("total", 0),
                "filtered_chunks": (
                    stats.get("filtered_too_short", 0)
                    + stats.get("filtered_table_figure", 0)
                    + stats.get("filtered_article_only", 0)
                    + stats.get("filtered_appendix", 0)
                ),
                "llm_input_chunks": llm_stats.get("total_input", 0)
                    - llm_stats.get("llm_skipped", 0),
                "llm_success_chunks": llm_stats.get("llm_success", 0),
                "llm_failed_chunks": llm_stats.get("llm_failed", 0),
                "llm_skipped_chunks": llm_stats.get("llm_skipped", 0),
                "suspicious_chunks": stats.get("suspicious", 0),
            },
            "output_summary": {
                **node_counts,
                "total_edges": len(results.get("edges", [])),
                "total_nodes": sum(node_counts.values()),
            },
            "extraction_counts": {
                "extracted_terms": len(results.get("terms", [])),
                "extracted_definitions": len(results.get("definitions", [])),
                "extracted_rules": len(results.get("rules", [])),
                "extracted_conditions": len(results.get("conditions", [])),
                "extracted_constraints": len(results.get("constraints", [])),
                "extracted_references": len(results.get("references", [])),
            },
            "performance_metrics": {
                "avg_latency_ms": extractor_stats.get("avg_latency_ms", 0),
                "total_latency_ms": extractor_stats.get("total_latency_ms", 0),
                "estimated_token_usage": extractor_stats.get("estimated_token_usage", 0),
                "failed_case_count": extractor_stats.get("failed_case_count", 0),
            },
            "schema_info": {
                "node_types": [
                    "Document", "StructuralUnit", "Term", "Definition",
                    "Rule", "Condition", "Constraint", "Reference",
                ],
                "edge_types": [
                    "CONTAINS", "DEFINES", "HAS_RULE", "APPLIES_TO",
                    "HAS_CONDITION", "HAS_CONSTRAINT", "REFERENCES", "SAME_AS",
                ],
            },
            "quality_metrics": {
                "avg_rule_confidence": self._avg_confidence(results.get("rules", [])),
                "avg_definition_confidence": self._avg_confidence(results.get("definitions", [])),
                "rules_with_subject": sum(1 for r in results.get("rules", []) if r.get("subject")),
                "rules_with_object": sum(1 for r in results.get("rules", []) if r.get("object")),
            },
            "architecture": {
                "mode": "LLM-first",
                "llm_model": "DeepSeek-V3.2",
                "rules_used_for": ["cleaning", "filtering", "validation", "normalization"],
                "rules_not_used_for": ["subject/action/object extraction", "rule triple generation"],
            },
            "limitations_and_next_steps": [
                "当前版本完全依赖 LLM 抽取，抽取质量取决于模型能力",
                "超长文本已切分为子块分别抽取，但可能丢失跨句语义",
                "证据文本校验仅检查是否存在于原文，未做精确匹配",
                "建议下一步：增加人工审核环节",
                "建议下一步：支持增量抽取和更新",
                "建议下一步：接入 Neo4j 图数据库",
            ],
        }

    @staticmethod
    def _avg_confidence(items: List[Dict]) -> float:
        if not items:
            return 0.0
        confidences = [
            item.get("confidence", 0)
            for item in items
            if item.get("confidence") is not None
        ]
        return round(sum(confidences) / len(confidences), 3) if confidences else 0.0
