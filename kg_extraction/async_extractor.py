import asyncio
import aiohttp
import logging
import time
import hashlib
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
import json
import os

from .schema import (
    DocumentNode, StructuralUnitNode, TermNode, DefinitionNode,
    RuleNode, ConditionNode, ConstraintNode, ReferenceNode, Edge,
    NodeType, EdgeType, RuleType, TermCategory, ConditionType,
    Comparator, UnitType, RefType,
)
from .normalizer import Normalizer
from .llm_provider import safe_parse_json, SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    chunk_id: str
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: str = ""
    latency_ms: float = 0.0
    from_cache: bool = False
    is_fallback: bool = False


MODALITY_KEYWORDS = {
    "应当": RuleType.OBLIGATION.value,
    "必须": RuleType.OBLIGATION.value,
    "不得": RuleType.PROHIBITION.value,
    "禁止": RuleType.PROHIBITION.value,
    "可以": RuleType.PERMISSION.value,
    "仅允许": RuleType.PERMISSION.value,
    "负责": RuleType.RESPONSIBILITY.value,
}

CONDITION_KEYWORDS = ["在", "除", "当", "只有", "符合", "适用"]

CONSTRAINT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(米|公里|千米|海里|英尺|公里/小时|节|日|天|个工作日|月|年|小时|分钟|秒|%|度)")


def rule_based_extract(chunk: Dict) -> Optional[Dict[str, Any]]:
    text = chunk.get("text", "")
    chunk_id = chunk.get("id", "")
    
    ARTICLE_PREFIX_PATTERN = re.compile(r"^(第[一二三四五六七八九十百千\d]+条)[，。、：:\s]")
    
    rules = []
    for keyword, rule_type in MODALITY_KEYWORDS.items():
        if keyword in text:
            pos = text.find(keyword)
            before = text[:pos].strip()
            after = text[pos + len(keyword):].strip()
            
            subject_parts = before.split("，")[-1].split("。")[-1] if before else ""
            subject = subject_parts.strip()[-30:] if len(subject_parts.strip()) > 30 else subject_parts.strip()
            
            subject = ARTICLE_PREFIX_PATTERN.sub("", subject).strip()
            
            action_obj = after[:100]
            obj = ""
            action = action_obj
            
            for marker in ["对", "向", "将", "把"]:
                idx = action_obj.find(marker)
                if idx >= 0 and idx < len(action_obj):
                    remaining = action_obj[idx + len(marker):idx + len(marker) + 60]
                    end_idx = min(len(remaining), 60)
                    for sep in ["。", "；", "，"]:
                        si = remaining.find(sep)
                        if 5 < si < end_idx:
                            end_idx = si
                            break
                    obj = remaining[:end_idx].strip()
                    action = action_obj[:len(action_obj) - len(obj)].rstrip(marker + " ")
                    break
            
            if len(action) > 100:
                for sep in ["。", "；", "，"]:
                    si = action.find(sep)
                    if 10 < si < 100:
                        action = action[:si]
                        break
            
            evidence_start = max(0, pos - 15)
            evidence_end = min(len(text), pos + 60)
            
            if action.strip():
                rules.append({
                    "rule_type": rule_type,
                    "modality": keyword,
                    "subject": subject or "",
                    "action": action.strip(),
                    "object": obj or "",
                    "confidence": 0.7,
                    "evidence_text": text[evidence_start:evidence_end],
                })
    
    conditions = []
    for kw in CONDITION_KEYWORDS:
        pattern_text = f".{{0,40}}{kw}.{{0,60}}"
        match = re.search(pattern_text, text)
        if match:
            conditions.append({
                "condition_type": ConditionType.SCOPE.value,
                "text": match.group(),
                "confidence": 0.7,
                "evidence_text": match.group(),
            })
    
    constraints = []
    for m in CONSTRAINT_PATTERN.finditer(text):
        constraints.append({
            "text": m.group(0),
            "comparator": Comparator.NONE.value,
            "value": m.group(1),
            "unit": m.group(2),
            "confidence": 0.75,
            "evidence_text": m.group(0),
        })
    
    if not rules and not conditions and not constraints:
        return None
    
    return {
        "should_extract": True,
        "reason": "fallback_rule_based",
        "definitions": [],
        "rules": rules,
        "conditions": conditions,
        "constraints": constraints,
        "references": [],
    }


class AsyncLLMProvider:
    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "",
        temperature: float = 0.05,
        max_tokens: int = 800,
        timeout: int = 25,
        max_concurrency: int = 3,
        max_retries: int = 1,
        enable_fallback: bool = True,
    ):
        # 从环境变量读取配置
        self.api_key = api_key or os.environ.get("SILICONFLOW_API_KEY", "")
        self.base_url = (base_url or os.environ.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")).rstrip("/")
        self.model = model or os.environ.get("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V3")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_concurrency = max_concurrency
        self.max_retries = max_retries
        self.enable_fallback = enable_fallback
        self._cache: Dict[str, Dict] = {}
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._stats = {
            "total_calls": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "retries": 0,
            "failures": 0,
            "fallbacks": 0,
        }

    @property
    def is_enabled(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _make_cache_key(text: str, category: str) -> str:
        content = f"{text}::{category}"
        return hashlib.md5(content.encode()).hexdigest()

    async def __aenter__(self):
        self._semaphore = asyncio.Semaphore(self.max_concurrency)
        connector = aiohttp.TCPConnector(limit=self.max_concurrency * 2)
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        self._session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()

    async def extract_chunk(
        self,
        chunk_id: str,
        text: str,
        category: str,
        metadata: Dict[str, Any],
    ) -> ExtractionResult:
        if not self.is_enabled:
            return ExtractionResult(
                chunk_id=chunk_id,
                success=False,
                error="API key not configured",
            )

        cache_key = self._make_cache_key(text, category)
        if cache_key in self._cache:
            self._stats["cache_hits"] += 1
            return ExtractionResult(
                chunk_id=chunk_id,
                success=True,
                result=self._cache[cache_key],
                from_cache=True,
            )

        self._stats["cache_misses"] += 1

        user_prompt = USER_PROMPT_TEMPLATE.format(
            chunk_id=chunk_id,
            doc_title=metadata.get("doc_title", ""),
            source_type=metadata.get("source_type", ""),
            source_file=metadata.get("source_file", ""),
            chapter=metadata.get("chapter", ""),
            section=metadata.get("section", ""),
            article_no=metadata.get("article_no", ""),
            article_num=metadata.get("article_num", ""),
            text=text[:2000],
            category=category,
        )

        for attempt in range(self.max_retries + 1):
            async with self._semaphore:
                start_time = time.time()
                try:
                    result_raw = await self._call_api(SYSTEM_PROMPT, user_prompt)
                    latency_ms = (time.time() - start_time) * 1000
                    
                    parsed, parse_status = safe_parse_json(result_raw)
                    
                    self._stats["total_calls"] += 1
                    if parsed:
                        self._cache[cache_key] = parsed
                        logger.info(f"[{chunk_id}] OK ({latency_ms:.0f}ms, parse={parse_status})")
                        return ExtractionResult(
                            chunk_id=chunk_id,
                            success=True,
                            result=parsed,
                            latency_ms=latency_ms,
                        )
                    else:
                        logger.warning(f"[{chunk_id}] PARSE_FAIL ({latency_ms:.0f}ms, reason={parse_status})")
                        
                        if self.enable_fallback:
                            self._stats["fallbacks"] += 1
                            fallback_result = rule_based_extract({
                                "id": chunk_id,
                                "text": text,
                                "_category": category,
                                "metadata": metadata,
                            })
                            if fallback_result:
                                logger.info(f"[{chunk_id}] FALLBACK_OK (rules={len(fallback_result['rules'])}, conds={len(fallback_result['conditions'])})")
                                return ExtractionResult(
                                    chunk_id=chunk_id,
                                    success=True,
                                    result=fallback_result,
                                    latency_ms=latency_ms,
                                    is_fallback=True,
                                )
                        
                        self._stats["failures"] += 1
                        return ExtractionResult(
                            chunk_id=chunk_id,
                            success=False,
                            error=f"parse_failed: {parse_status}",
                            latency_ms=latency_ms,
                        )
                        
                except asyncio.TimeoutError:
                    self._stats["retries"] += 1
                    logger.warning(f"[{chunk_id}] TIMEOUT attempt {attempt+1}")
                    if attempt == self.max_retries:
                        if self.enable_fallback:
                            self._stats["fallbacks"] += 1
                            fallback_result = rule_based_extract({
                                "id": chunk_id,
                                "text": text,
                                "_category": category,
                                "metadata": metadata,
                            })
                            if fallback_result:
                                return ExtractionResult(
                                    chunk_id=chunk_id,
                                    success=True,
                                    result=fallback_result,
                                    is_fallback=True,
                                )
                        self._stats["failures"] += 1
                        return ExtractionResult(
                            chunk_id=chunk_id,
                            success=False,
                            error="timeout",
                        )
                    await asyncio.sleep(0.5)
                except Exception as e:
                    self._stats["retries"] += 1
                    logger.warning(f"[{chunk_id}] ERROR: {e}, attempt {attempt+1}")
                    if attempt == self.max_retries:
                        if self.enable_fallback:
                            self._stats["fallbacks"] += 1
                            fallback_result = rule_based_extract({
                                "id": chunk_id,
                                "text": text,
                                "_category": category,
                                "metadata": metadata,
                            })
                            if fallback_result:
                                return ExtractionResult(
                                    chunk_id=chunk_id,
                                    success=True,
                                    result=fallback_result,
                                    is_fallback=True,
                                )
                        self._stats["failures"] += 1
                        return ExtractionResult(
                            chunk_id=chunk_id,
                            success=False,
                            error=str(e)[:100],
                        )
                    await asyncio.sleep(0.5)

        return ExtractionResult(chunk_id=chunk_id, success=False, error="unknown")

    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        async with self._session.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
        ) as response:
            response.raise_for_status()
            data = await response.json()
            content = data["choices"][0]["message"]["content"]
            
            if not content or not content.strip():
                logger.warning(f"API returned empty/None content. Full response keys: {list(data.keys())}")
                if "choices" in data:
                    logger.warning(f"  choices[0].message: {data['choices'][0].get('message', {})}")
                return ""
            
            logger.debug(f"API response length: {len(content)}, preview: {content[:200]}...")
            return content

    def get_stats(self) -> Dict[str, Any]:
        total = self._stats["total_calls"]
        return {
            **self._stats,
            "success_rate": round((total - self._stats["failures"]) / max(total, 1) * 100, 1),
        }


class AsyncKnowledgeExtractor:
    def __init__(
        self,
        llm_provider: AsyncLLMProvider,
        normalizer: Optional[Normalizer] = None,
        merge_short_chunks: bool = True,
        short_chunk_threshold: int = 100,
    ):
        self.llm_provider = llm_provider
        self.normalizer = normalizer or Normalizer()
        self.merge_short_chunks = merge_short_chunks
        self.short_chunk_threshold = short_chunk_threshold
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

    async def extract_all_async(
        self,
        chunks: List[Dict[str, Any]],
        batch_size: int = 10,
    ) -> Dict[str, int]:
        logger.info("Starting async LLM-first knowledge graph extraction...")
        logger.info(f"  Batch size: {batch_size}, Max concurrency: {self.llm_provider.max_concurrency}")
        
        self._extract_structural_layer(chunks)

        chunks_to_process = self._prepare_chunks(chunks)
        total = len(chunks_to_process)
        success_count = 0
        fail_count = 0
        fallback_count = 0

        start_time = time.time()
        
        for batch_start in range(0, total, batch_size):
            batch_end = min(batch_start + batch_size, total)
            batch = chunks_to_process[batch_start:batch_end]
            
            batch_start_time = time.time()
            tasks = [
                self.llm_provider.extract_chunk(
                    chunk_id=c.get("id", f"chunk_{i}"),
                    text=c.get("text", ""),
                    category=c.get("_category", ""),
                    metadata=c.get("metadata", {}),
                )
                for i, c in enumerate(batch, start=batch_start)
            ]
            
            results = await asyncio.gather(*tasks)
            batch_latency = (time.time() - batch_start_time) * 1000
            
            for chunk, result in zip(batch, results):
                if result.success and result.result:
                    self._process_llm_result(chunk, result.result)
                    success_count += 1
                    if result.is_fallback:
                        fallback_count += 1
                else:
                    self._log_failed_case(chunk, result.error)
                    fail_count += 1
                
                if result.latency_ms > 0:
                    self._latencies.append(result.latency_ms)
            
            elapsed = time.time() - start_time
            avg_latency = sum(self._latencies) / len(self._latencies) if self._latencies else 0
            logger.info(
                f"Batch progress: {batch_end}/{total}, "
                f"success={success_count}, fail={fail_count}, fallback={fallback_count}, "
                f"batch_latency={batch_latency:.0f}ms, "
                f"avg_latency={avg_latency:.0f}ms, "
                f"elapsed={elapsed:.1f}s"
            )

        provider_stats = self.llm_provider.get_stats()
        logger.info(f"Async extraction complete. Success: {success_count}, Failed: {fail_count}, Fallback: {fallback_count}")
        logger.info(f"  Cache hits: {provider_stats['cache_hits']}, Misses: {provider_stats['cache_misses']}")
        logger.info(f"  Total API calls: {provider_stats['total_calls']}, Retries: {provider_stats['retries']}")
        logger.info(f"Nodes: D={len(self.documents)}, S={len(self.structural_units)}, "
                     f"T={len(self.terms)}, Df={len(self.definitions)}, R={len(self.rules)}, "
                     f"C={len(self.conditions)}, Cs={len(self.constraints)}, Ref={len(self.references)}, "
                     f"E={len(self.edges)}")

        return {
            "llm_success": success_count,
            "llm_failed": fail_count,
            "total_input": total,
            "cache_hits": provider_stats["cache_hits"],
            "cache_misses": provider_stats["cache_misses"],
            "fallbacks": fallback_count,
        }

    def _prepare_chunks(self, chunks: List[Dict]) -> List[Dict]:
        if not self.merge_short_chunks:
            return [c for c in chunks if c.get("_category") != "noise" and not c.get("_flags", {}).get("too_short")]

        prepared = []
        merge_buffer = []
        merge_metadata = {}

        for chunk in chunks:
            flags = chunk.get("_flags", {})
            if chunk.get("_category") == "noise":
                continue
            if flags.get("too_short") or flags.get("is_table_or_figure") or flags.get("is_appendix_block"):
                continue

            text = chunk.get("text", "")
            if len(text) < self.short_chunk_threshold and self.merge_short_chunks:
                merge_buffer.append(chunk)
                if not merge_metadata:
                    merge_metadata = chunk.get("metadata", {}).copy()
            else:
                if merge_buffer:
                    merged = self._merge_chunks(merge_buffer, merge_metadata)
                    prepared.append(merged)
                    merge_buffer = []
                    merge_metadata = {}
                prepared.append(chunk)

        if merge_buffer:
            merged = self._merge_chunks(merge_buffer, merge_metadata)
            prepared.append(merged)

        return prepared

    @staticmethod
    def _merge_chunks(chunks: List[Dict], metadata: Dict) -> Dict:
        merged_text = "\n".join(c.get("text", "") for c in chunks)
        merged_id = "_".join(c.get("id", "") for c in chunks[:3])
        if len(chunks) > 3:
            merged_id += f"_..._{len(chunks)}"
        return {
            "id": f"merged_{merged_id}",
            "text": merged_text,
            "metadata": metadata,
            "_category": "merged",
            "_flags": {},
            "_details": [],
        }

    def _process_llm_result(self, chunk: Dict, llm_result: Dict) -> None:
        if not llm_result.get("should_extract", True):
            return

        chunk_id = chunk.get("id", "")
        meta = chunk.get("metadata", {})
        article_no = meta.get("article_no", "")
        doc_title = meta.get("doc_title", "")
        text = chunk.get("text", "")
        art_node = self._get_article_node(doc_title, article_no)

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
            norm_name, canonical = self.normalizer.normalize_entity(term_name)
            term_cat = d.get("category", TermCategory.GENERIC.value)
            term = TermNode(
                id=term_id,
                name=term_name,
                normalized_name=canonical or norm_name,
                category=term_cat,
                chunk_id=chunk_id,
                evidence_text=evidence,
                confidence=d.get("confidence", 0.9),
            )
            self.terms.append(term)

            self.edges.append(Edge(
                source_id=term_id,
                target_id=def_id,
                relation_type=EdgeType.DEFINES.value,
                chunk_id=chunk_id,
                article_no=article_no,
                doc_title=doc_title,
                evidence_text=evidence,
            ))

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
                confidence=r.get("confidence", 0.85),
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
                confidence=c.get("confidence", 0.8),
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
                confidence=cs.get("confidence", 0.85),
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
                confidence=ref.get("confidence", 0.8),
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
            "text": chunk.get("text", "")[:300],
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
            "failed_case_count": len(self._failed_cases),
        }
