import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)


class Validator:
    def __init__(self):
        self.warnings: List[str] = []
        self.errors: List[str] = []

    def validate_results(self, results: Dict[str, List]) -> Dict[str, Any]:
        self.warnings.clear()
        self.errors.clear()

        node_counts = {k: len(v) for k, v in results.items() if k != "edges"}
        edge_count = len(results.get("edges", []))

        self._validate_nodes(results)
        self._validate_edges(results)
        self._cross_validate(results)

        return {
            "node_counts": node_counts,
            "edge_count": edge_count,
            "warnings": self.warnings,
            "errors": self.errors,
            "is_valid": len(self.errors) == 0,
            "warning_count": len(self.warnings),
        }

    def _validate_nodes(self, results: Dict[str, Any]) -> None:
        for node_type, nodes in results.items():
            if node_type == "edges":
                continue
            if not isinstance(nodes, list):
                self.errors.append(f"Node type '{node_type}' is not a list")
                continue
            ids_seen = set()
            for i, node in enumerate(nodes):
                if not isinstance(node, dict):
                    self.errors.append(f"{node_type}[{i}] is not a dict")
                    continue
                nid = node.get("id", "")
                if not nid:
                    self.warnings.append(f"{node_type}[{i}] missing id")
                elif nid in ids_seen:
                    self.warnings.append(f"{node_type}[{i}] duplicate id: {nid}")
                else:
                    ids_seen.add(nid)

                confidence = node.get("confidence")
                if confidence is not None and (confidence < 0 or confidence > 1):
                    self.warnings.append(f"{node_type}[{nid}] invalid confidence: {confidence}")

    def _validate_edges(self, results: Dict[str, Any]) -> None:
        edges = results.get("edges", [])
        valid_relations = {
            "CONTAINS", "DEFINES", "HAS_RULE", "APPLIES_TO",
            "HAS_CONDITION", "HAS_CONSTRAINT", "REFERENCES", "SAME_AS",
        }
        all_node_ids = set()
        for node_type, nodes in results.items():
            if node_type != "edges":
                for n in nodes:
                    if isinstance(n, dict) and n.get("id"):
                        all_node_ids.add(n["id"])

        for i, edge in enumerate(edges):
            if not isinstance(edge, dict):
                self.errors.append(f"edges[{i}] is not a dict")
                continue
            src = edge.get("source_id", "")
            tgt = edge.get("target_id", "")
            rel = edge.get("relation_type", "")

            if src and src not in all_node_ids:
                self.warnings.append(f"edges[{i}] source_id '{src}' not found in nodes")
            if tgt and tgt not in all_node_ids:
                self.warnings.append(f"edges[{i}] target_id '{tgt}' not found in nodes")
            if rel and rel not in valid_relations:
                self.warnings.append(f"edges[{i}] unknown relation type: {rel}")

    def _cross_validate(self, results: Dict[str, Any]) -> None:
        terms = results.get("terms", [])
        definitions = results.get("definitions", [])
        term_names = {t["name"] for t in terms if isinstance(t, dict)}
        def_term_names = {d.get("term_name", "") for d in definitions if isinstance(d, dict)}

        orphan_defs = def_term_names - term_names
        if orphan_defs:
            self.warnings.append(
                f"{len(orphan_defs)} definitions reference undefined terms"
            )

        rules = results.get("rules", [])
        empty_action_rules = sum(1 for r in rules if isinstance(r, dict) and not r.get("action"))
        if empty_action_rules > 0:
            self.warnings.append(f"{empty_action_rules} rules have empty action field")

    @staticmethod
    def check_rule_quality(rule: Dict[str, Any]) -> Tuple[bool, str]:
        issues = []
        if not rule.get("subject"):
            issues.append("missing_subject")
        if not rule.get("action"):
            issues.append("missing_action")
        modality = rule.get("modality", "")
        valid_modalities = {"应当", "不得", "可以", "负责", "必须", "禁止", "仅允许"}
        if modality and modality not in valid_modalities:
            issues.append(f"invalid_modality:{modality}")
        return len(issues) == 0, ",".join(issues) if issues else "ok"

    @staticmethod
    def check_definition_quality(defn: Dict[str, Any]) -> Tuple[bool, str]:
        if not defn.get("term_name"):
            return False, "missing_term_name"
        if not defn.get("definition_text") or len(defn["definition_text"]) < 4:
            return False, "too_short_definition"
        return True, "ok"
