import logging
import time
from typing import Dict, Any, List, Optional, Tuple
import json

from .schema import (
    DocumentNode, StructuralUnitNode, TermNode, DefinitionNode,
    RuleNode, ConditionNode, ConstraintNode, ReferenceNode, Edge,
    NodeType, EdgeType, RuleType, TermCategory, ConditionType,
    Comparator, UnitType, RefType,
)
from .normalizer import Normalizer
from .llm_provider import LLMProvider

logger = logging.getLogger(__name__)


class KnowledgeExtractor:
    def __init__(self, llm_provider: LLMProvider, normalizer: Optional[Normalizer] = None):
        self.llm_provider = llm_provider
        self.normalizer = normalizer or Normalizer()
        self.documents: List[DocumentNode] = []
        self.structural_units: List[StructuralUnitNode] = []
        self.terms: List[TermNode] = []
        self.definitions: List[DefinitionNode] = []
        self.rules: List[RuleNode] = []
        self.conditions: List[ConditionNode] = []
        self.constraints: List[ConstraintNode] = []
        self.references: List[ReferenceNode] = []
        self.edges: List[Edge] = []
        self._doc_cache: Dict[str, DocumentNode] = {}
        self._article_cache: Dict[str, StructuralUnitNode] = {}
        self._failed_cases: List[Dict[str, Any]] = []
        self._latencies: List[float] = []
        self._total_tokens_estimate = 0

    def extract_all_with_llm(
        self,
        chunks: List[Dict[str, Any]],
        delay_seconds: float = 0.5,
        max_retries: int = 2,
    ) -> Dict[str, int]:
        logger.info("Starting LLM-first knowledge graph extraction...")
        self._extract_structural_layer(chunks)

        total = len(chunks)
        success_count = 0
        fail_count = 0
        skip_count = 0

        for i, chunk in enumerate(chunks):
            chunk_id = chunk.get("id", f"chunk_{i}")
            text = chunk.get("text", "")
            category = chunk.get("_category", "")
            flags = chunk.get("_flags", {})
            metadata = chunk.get("metadata", {})

            if category in ("noise",):
                skip_count += 1
                continue

            if flags.get("too_short", False):
                skip_count += 1
                continue

            if flags.get("is_table_or_figure", False):
                skip_count += 1
                continue

            if flags.get("is_appendix_block", False):
                skip_count += 1
                continue

            chunks_to_process = self._split_long_text(chunk) if flags.get("review_required") else [chunk]

            chunk_success = False
            for sub_chunk in chunks_to_process:
                start_time = time.time()
                result = self._extract_single_chunk(sub_chunk, max_retries)
                latency = (time.time() - start_time) * 1000
                self._latencies.append(latency)

                if result:
                    self._process_llm_result(sub_chunk, result)
                    chunk_success = True
                else:
                    self._log_failed_case(sub_chunk, "LLM extraction failed after retries")

            if chunk_success:
                success_count += 1
            else:
                fail_count += 1

            self._total_tokens_estimate += len(text) // 2

            if delay_seconds > 0 and i < total - 1:
                time.sleep(delay_seconds)

            if (i + 1) % 50 == 0:
                logger.info(f"LLM extraction progress: {i+1}/{total}, success={success_count}, fail={fail_count}, skip={skip_count}")

        logger.info(f"LLM extraction complete. Success: {success_count}, Failed: {fail_count}, Skipped: {skip_count}")
        logger.info(f"Nodes: D={len(self.documents)}, S={len(self.structural_units)}, "
                     f"T={len(self.terms)}, Df={len(self.definitions)}, R={len(self.rules)}, "
                     f"C={len(self.conditions)}, Cs={len(self.constraints)}, Ref={len(self.references)}, "
                     f"E={len(self.edges)}")

        return {
            "llm_success": success_count,
            "llm_failed": fail_count,
            "llm_skipped": skip_count,
            "total_input": total,
        }

    def _split_long_text(self, chunk: Dict) -> List[Dict]:
        text = chunk.get("text", "")
        if len(text) <= 3000:
            return [chunk]

        sentences = text.replace("。", "。\n").replace("；", "；\n").split("\n")
        chunks_split = []
        current_text = ""
        sub_idx = 0

        for sent in sentences:
            if len(current_text) + len(sent) > 2500 and current_text:
                sub_chunk = chunk.copy()
                sub_chunk["id"] = f"{chunk['id']}_sub{sub_idx}"
                sub_chunk["text"] = current_text.strip()
                chunks_split.append(sub_chunk)
                current_text = sent
                sub_idx += 1
            else:
                current_text += sent

        if current_text.strip():
            sub_chunk = chunk.copy()
            sub_chunk["id"] = f"{chunk['id']}_sub{sub_idx}"
            sub_chunk["text"] = current_text.strip()
            chunks_split.append(sub_chunk)

        logger.debug(f"Split long chunk {chunk['id']} into {len(chunks_split)} sub-chunks")
        return chunks_split

    def _extract_single_chunk(self, chunk: Dict, max_retries: int) -> Optional[Dict]:
        chunk_id = chunk.get("id", "")
        text = chunk.get("text", "")
        category = chunk.get("_category", "")
        metadata = chunk.get("metadata", {})

        for attempt in range(max_retries + 1):
            try:
                result = self.llm_provider.extract_chunk(
                    chunk_id=chunk_id,
                    text=text,
                    category=category,
                    metadata=metadata,
                )
                if result:
                    if self._validate_llm_result(result, text):
                        return result
                    else:
                        logger.warning(f"Validation failed for {chunk_id}, attempt {attempt+1}")
                else:
                    logger.warning(f"Empty result for {chunk_id}, attempt {attempt+1}")
            except Exception as e:
                logger.warning(f"LLM call failed for {chunk_id}, attempt {attempt+1}: {e}")

            if attempt < max_retries:
                time.sleep(1)

        return None

    def _validate_llm_result(self, result: Dict, original_text: str) -> bool:
        if not isinstance(result, dict):
            return False

        if not result.get("should_extract", True):
            return True

        for rule in result.get("rules", []):
            evidence = rule.get("evidence_text", "")
            if evidence and evidence not in original_text:
                logger.warning(f"Evidence not found in original text: {evidence[:50]}...")

        for term in result.get("terms", []):
            if not term.get("name"):
                return False

        return True

    def _process_llm_result(self, chunk: Dict, llm_result: Dict) -> None:
        if not llm_result.get("should_extract", True):
            return

        chunk_id = chunk.get("id", "")
        meta = chunk.get("metadata", {})
        article_no = meta.get("article_no", "")
        doc_title = meta.get("doc_title", "")
        text = chunk.get("text", "")
        art_node = self._get_article_node(doc_title, article_no)

        for t in llm_result.get("terms", []):
            term_name = t.get("name", "")
            if not term_name or len(term_name) < 2:
                continue
            norm_name, canonical = self.normalizer.normalize_entity(term_name)
            term_cat = t.get("category", TermCategory.GENERIC.value)
            term_id = self._make_id("term", f"{term_name}_{chunk_id}")
            evidence = t.get("evidence_text", text[:100])

            term = TermNode(
                id=term_id,
                name=term_name,
                normalized_name=canonical or norm_name,
                category=term_cat,
                chunk_id=chunk_id,
                evidence_text=evidence,
                aliases=t.get("aliases", []),
                confidence=t.get("confidence", 0.9),
            )
            self.terms.append(term)

            if art_node:
                self.edges.append(Edge(
                    source_id=art_node.id,
                    target_id=term_id,
                    relation_type=EdgeType.HAS_RULE.value,
                    chunk_id=chunk_id,
                    article_no=article_no,
                    doc_title=doc_title,
                    evidence_text=evidence,
                ))

        for d in llm_result.get("definitions", []):
            term_name = d.get("term_name", "")
            def_text = d.get("definition_text", "")
            if not term_name or not def_text:
                continue
            def_id = self._make_id("def", f"{term_name}_{chunk_id}")
            evidence = d.get("evidence_text", def_text[:100])

            definition = DefinitionNode(
                id=def_id,
                term_name=term_name,
                definition_text=def_text,
                chunk_id=chunk_id,
                evidence_text=evidence,
                confidence=d.get("confidence", 0.9),
            )
            self.definitions.append(definition)

            term_id = self._make_id("term", f"{term_name}_{chunk_id}")
            self.edges.append(Edge(
                source_id=term_id,
                target_id=def_id,
                relation_type=EdgeType.DEFINES.value,
                chunk_id=chunk_id,
                article_no=article_no,
                doc_title=doc_title,
                evidence_text=evidence,
            ))

        for r in llm_result.get("rules", []):
            modality = r.get("modality", "")
            subject = r.get("subject", "")
            action = r.get("action", "")
            obj = r.get("object", "")
            rule_type = r.get("rule_type", "")
            evidence = r.get("evidence_text", text[:150])

            if not modality:
                continue
            if not rule_type:
                rule_type = self._map_rule_type(modality)

            rule_id = self._make_id("rule", f"{chunk_id}_{len(self.rules)}")

            norm_subj = self.normalizer.normalize_subject(subject) if subject else ""
            norm_action = self.normalizer.normalize_text(action) if action else ""
            norm_obj = self.normalizer.normalize_text(obj) if obj else ""

            rule = RuleNode(
                id=rule_id,
                rule_type=rule_type,
                modality=modality,
                subject=subject,
                action=action,
                object=obj,
                chunk_id=chunk_id,
                evidence_text=evidence,
                normalized_subject=norm_subj,
                normalized_action=norm_action,
                normalized_object=norm_obj,
                confidence=r.get("confidence", 0.9),
            )
            self.rules.append(rule)

            if art_node:
                self.edges.append(Edge(
                    source_id=art_node.id,
                    target_id=rule_id,
                    relation_type=EdgeType.HAS_RULE.value,
                    chunk_id=chunk_id,
                    article_no=article_no,
                    doc_title=doc_title,
                    evidence_text=evidence,
                ))

        for c in llm_result.get("conditions", []):
            cond_text = c.get("text", "")
            if not cond_text:
                continue
            cond_type = c.get("condition_type", ConditionType.SCOPE.value)
            cond_id = self._make_id("cond", f"{chunk_id}_{len(self.conditions)}")
            evidence = c.get("evidence_text", cond_text)

            condition = ConditionNode(
                id=cond_id,
                text=cond_text,
                condition_type=cond_type,
                chunk_id=chunk_id,
                evidence_text=evidence,
                confidence=c.get("confidence", 0.9),
            )
            self.conditions.append(condition)

            if art_node:
                self.edges.append(Edge(
                    source_id=art_node.id,
                    target_id=cond_id,
                    relation_type=EdgeType.HAS_CONDITION.value,
                    chunk_id=chunk_id,
                    article_no=article_no,
                    doc_title=doc_title,
                    evidence_text=evidence,
                ))

        for cs in llm_result.get("constraints", []):
            cs_text = cs.get("text", "")
            if not cs_text:
                continue
            cs_id = self._make_id("cons", f"{chunk_id}_{len(self.constraints)}")
            evidence = cs.get("evidence_text", cs_text)

            constraint = ConstraintNode(
                id=cs_id,
                text=cs_text,
                comparator=cs.get("comparator", Comparator.NONE.value),
                value=cs.get("value", ""),
                unit=cs.get("unit", ""),
                chunk_id=chunk_id,
                evidence_text=evidence,
                confidence=cs.get("confidence", 0.9),
            )
            self.constraints.append(constraint)

            if art_node:
                self.edges.append(Edge(
                    source_id=art_node.id,
                    target_id=cs_id,
                    relation_type=EdgeType.HAS_CONSTRAINT.value,
                    chunk_id=chunk_id,
                    article_no=article_no,
                    doc_title=doc_title,
                    evidence_text=evidence,
                ))

        for ref in llm_result.get("references", []):
            ref_text = ref.get("ref_text", "")
            if not ref_text:
                continue
            ref_id = self._make_id("ref", f"{chunk_id}_{len(self.references)}")
            evidence = ref.get("evidence_text", ref_text)

            reference = ReferenceNode(
                id=ref_id,
                ref_type=ref.get("ref_type", RefType.REGULATION.value),
                ref_text=ref_text,
                chunk_id=chunk_id,
                evidence_text=evidence,
                confidence=ref.get("confidence", 0.9),
            )
            self.references.append(reference)

            if art_node:
                self.edges.append(Edge(
                    source_id=art_node.id,
                    target_id=ref_id,
                    relation_type=EdgeType.REFERENCES.value,
                    chunk_id=chunk_id,
                    article_no=article_no,
                    doc_title=doc_title,
                    evidence_text=evidence,
                ))

    def _log_failed_case(self, chunk: Dict, reason: str) -> None:
        self._failed_cases.append({
            "chunk_id": chunk.get("id", ""),
            "text": chunk.get("text", "")[:500],
            "reason": reason,
            "metadata": chunk.get("metadata", {}),
        })

    def _extract_structural_layer(self, chunks: List[Dict]) -> None:
        seen_docs = set()
        seen_articles = set()

        for chunk in chunks:
            meta = chunk.get("metadata", {})
            doc_title = meta.get("doc_title", "")

            if doc_title and doc_title not in seen_docs:
                doc_id = self._make_id("doc", doc_title)
                doc = DocumentNode(
                    id=doc_id,
                    doc_title=doc_title,
                    source_file=meta.get("source_file", ""),
                    source_type=meta.get("source_type", ""),
                )
                self.documents.append(doc)
                self._doc_cache[doc_title] = doc
                seen_docs.add(doc_title)

            article_no = meta.get("article_no", "")
            chapter = meta.get("chapter", "")
            section = meta.get("section", "")
            article_key = f"{doc_title}::{article_no}"

            if article_no and article_key not in seen_articles:
                art_id = self._make_id("art", article_key)
                unit = StructuralUnitNode(
                    id=art_id,
                    unit_type=UnitType.ARTICLE.value,
                    title=article_no,
                    chapter=chapter,
                    section=section,
                    article_no=article_no,
                    article_num=meta.get("article_num", ""),
                    doc_title=doc_title,
                )
                self.structural_units.append(unit)
                self._article_cache[article_key] = unit
                seen_articles.add(article_key)

                if self._doc_cache.get(doc_title):
                    self.edges.append(Edge(
                        source_id=self._doc_cache[doc_title].id,
                        target_id=art_id,
                        relation_type=EdgeType.CONTAINS.value,
                        chunk_id=chunk.get("id", ""),
                        article_no=article_no,
                        doc_title=doc_title,
                        evidence_text=chunk.get("text", "")[:100],
                    ))

                if section and chapter:
                    sec_key = f"{doc_title}::{chapter}::{section}"
                    if sec_key not in seen_articles:
                        sec_id = self._make_id("sec", sec_key)
                        sec_unit = StructuralUnitNode(
                            id=sec_id,
                            unit_type=UnitType.SECTION.value,
                            title=section,
                            chapter=chapter,
                            section=section,
                            article_no="",
                            article_num="",
                            doc_title=doc_title,
                        )
                        self.structural_units.append(sec_unit)
                        seen_articles.add(sec_key)

                        if self._doc_cache.get(doc_title):
                            self.edges.append(Edge(
                                source_id=self._doc_cache[doc_title].id,
                                target_id=sec_id,
                                relation_type=EdgeType.CONTAINS.value,
                                chunk_id=chunk.get("id", ""),
                                article_no="",
                                doc_title=doc_title,
                                evidence_text=f"{chapter} - {section}",
                            ))

    def _get_article_node(self, doc_title: str, article_no: str) -> Optional[StructuralUnitNode]:
        key = f"{doc_title}::{article_no}"
        return self._article_cache.get(key)

    @staticmethod
    def _make_id(prefix: str, seed: str) -> str:
        return f"{prefix}_{hash(seed) % 10**10:010d}"

    @staticmethod
    def _map_rule_type(modality: str) -> str:
        mapping = {
            "应当": RuleType.OBLIGATION.value,
            "必须": RuleType.OBLIGATION.value,
            "不得": RuleType.PROHIBITION.value,
            "禁止": RuleType.PROHIBITION.value,
            "可以": RuleType.PERMISSION.value,
            "仅允许": RuleType.PERMISSION.value,
            "负责": RuleType.RESPONSIBILITY.value,
        }
        return mapping.get(modality, RuleType.REQUIREMENT.value)

    def get_results(self) -> Dict[str, List]:
        return {
            "documents": [d.to_dict() for d in self.documents],
            "structural_units": [s.to_dict() for s in self.structural_units],
            "terms": [t.to_dict() for t in self.terms],
            "definitions": [d.to_dict() for d in self.definitions],
            "rules": [r.to_dict() for r in self.rules],
            "conditions": [c.to_dict() for c in self.conditions],
            "constraints": [cs.to_dict() for cs in self.constraints],
            "references": [ref.to_dict() for ref in self.references],
            "edges": [e.to_dict() for e in self.edges],
        }

    def get_failed_cases(self) -> List[Dict[str, Any]]:
        return self._failed_cases

    def get_stats(self) -> Dict[str, Any]:
        avg_latency = sum(self._latencies) / len(self._latencies) if self._latencies else 0
        return {
            "avg_latency_ms": round(avg_latency, 2),
            "total_latency_ms": round(sum(self._latencies), 2),
            "estimated_token_usage": self._total_tokens_estimate,
            "failed_case_count": len(self._failed_cases),
        }
