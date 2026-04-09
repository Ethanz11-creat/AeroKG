import re
import logging
from typing import Dict, Any, List, Set, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class ChunkCategory(Enum):
    DEFINITION = "definition"
    RULE = "rule"
    CONDITION = "condition"
    STRUCTURAL = "structural"
    NOISE = "noise"
    REVIEW_REQUIRED = "review_required"


class RuleModality(Enum):
    SHOULD = "应当"
    MUST_NOT = "不得"
    MAY = "可以"
    RESPONSIBLE_FOR = "负责"
    MUST = "必须"
    FORBIDDEN = "禁止"
    ONLY_ALLOW = "仅允许"


DEFINITION_PATTERNS = [
    re.compile(r"是指"),
    re.compile(r"术语的含义"),
    re.compile(r"(?:指|定义|含义|为)[，,：:]\s*(?:本规则|本条例|本办法)"),
    re.compile(r'[""「」](.+?)[""「」]\s*(?:是指|指|定义为|的含义是)'),
]

MODALITY_KEYWORDS = {
    "应当": RuleModality.SHOULD,
    "不得": RuleModality.MUST_NOT,
    "可以": RuleModality.MAY,
    "负责": RuleModality.RESPONSIBLE_FOR,
    "必须": RuleModality.MUST,
    "禁止": RuleModality.FORBIDDEN,
    "仅允许": RuleModality.ONLY_ALLOW,
}

CONDITION_PATTERNS = [
    re.compile(r"在.{0,30}(情况下|情形下|条件|范围内|期间)"),
    re.compile(r"除.{0,50}(外)"),
    re.compile(r"当.{0,20}(时)"),
    re.compile(r"只有.{0,20}(方可|才)"),
    re.compile(r"符合.{0,20}(条件|要求|规定)"),
    re.compile(r"适用(?:于)?(?:本规则|本条例|本办法)"),
]

CONSTRAINT_VALUE_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*"
    r"(米|公里|千米|海里|英尺|公里/小时|节|日|天|个工作日|月|年|小时|分钟|秒|%|度|摄氏度|人|架次|次|个|项|万元|兆赫兹|MHz|kHz|Hz)"
)

ARTICLE_ONLY_PATTERN = re.compile(r"^第[一二三四五六七八九十百千\d]+条\s*$")


class ChunkClassifier:
    def __init__(self):
        self._modalities = MODALITY_KEYWORDS

    def classify(self, chunk: Dict[str, Any], flags: Dict[str, Any]) -> Tuple[ChunkCategory, List[Dict]]:
        text = chunk.get("text", "")

        if flags.get("too_short", False):
            return ChunkCategory.NOISE, []
        if flags.get("is_table_or_figure", False):
            return ChunkCategory.NOISE, []
        if ARTICLE_ONLY_PATTERN.match(text.strip()):
            return ChunkCategory.NOISE, []
        if flags.get("is_appendix_block", False):
            return ChunkCategory.NOISE, []

        if flags.get("review_required", False):
            return ChunkCategory.REVIEW_REQUIRED, []

        found_modalities = self._detect_modalities(text)
        found_definitions = self._detect_definitions(text)
        found_conditions = self._detect_conditions(text)

        if found_definitions and not found_modalities:
            return ChunkCategory.DEFINITION, [{"type": "definition", "matches": found_definitions}]
        if found_modalities:
            extras = {}
            if found_conditions:
                extras["conditions"] = found_conditions
            return ChunkCategory.RULE, [{"type": "rule", "modalities": found_modalities, **extras}]

        if found_conditions:
            return ChunkCategory.CONDITION, [{"type": "condition", "matches": found_conditions}]

        return ChunkCategory.STRUCTURAL, []

    def _detect_modalities(self, text: str) -> List[Dict]:
        results = []
        for keyword, modality in self._modalities.items():
            positions = [m.start() for m in re.finditer(re.escape(keyword), text)]
            for pos in positions:
                context_start = max(0, pos - 10)
                context_end = min(len(text), pos + len(keyword) + 40)
                context = text[context_start:context_end]
                results.append({
                    "keyword": keyword,
                    "modality": modality.value,
                    "position": pos,
                    "context": context.strip(),
                })
        return results

    def _detect_definitions(self, text: str) -> List[Dict]:
        results = []
        for pat in DEFINITION_PATTERNS:
            matches = pat.finditer(text)
            for m in matches:
                results.append({
                    "pattern": pat.pattern[:40],
                    "match_text": m.group()[:80],
                    "start": m.start(),
                    "end": m.end(),
                })
        return results

    def _detect_conditions(self, text: str) -> List[Dict]:
        results = []
        for pat in CONDITION_PATTERNS:
            matches = pat.finditer(text)
            for m in matches:
                results.append({
                    "pattern": pat.pattern[:40],
                    "match_text": m.group()[:100],
                    "start": m.start(),
                    "end": m.end(),
                })
        return results

    @staticmethod
    def detect_constraints(text: str) -> List[Dict]:
        results = []
        for m in CONSTRAINT_VALUE_PATTERN.finditer(text):
            results.append({
                "full_match": m.group(0),
                "value": m.group(1),
                "unit": m.group(2),
                "position": m.start(),
            })
        return results

    @staticmethod
    def filter_and_validate(chunks: List[Dict[str, Any]], cleaner) -> Tuple[List[Dict], Dict[str, int]]:
        stats = {
            "total": len(chunks),
            "filtered_too_short": 0,
            "filtered_table_figure": 0,
            "filtered_article_only": 0,
            "filtered_appendix": 0,
            "review_required": 0,
            "suspicious": 0,
            "passed": 0,
            "definition_chunks": 0,
            "rule_chunks": 0,
            "condition_chunks": 0,
        }

        classifier = ChunkClassifier()
        passed = []

        for chunk in chunks:
            cleaned_chunk, flags = cleaner.clean(chunk)

            if flags.get("suspicious_article_match"):
                stats["suspicious"] += 1

            category, details = classifier.classify(cleaned_chunk, flags)
            cleaned_chunk["_category"] = category.value
            cleaned_chunk["_flags"] = flags
            cleaned_chunk["_details"] = details

            if category == ChunkCategory.NOISE:
                if flags.get("too_short"):
                    stats["filtered_too_short"] += 1
                elif flags.get("is_table_or_figure"):
                    stats["filtered_table_figure"] += 1
                elif flags.get("is_appendix_block"):
                    stats["filtered_appendix"] += 1
                else:
                    stats["filtered_article_only"] += 1
            elif category == ChunkCategory.REVIEW_REQUIRED:
                stats["review_required"] += 1
                passed.append(cleaned_chunk)
            else:
                stats["passed"] += 1
                passed.append(cleaned_chunk)
                if category == ChunkCategory.DEFINITION:
                    stats["definition_chunks"] += 1
                elif category == ChunkCategory.RULE:
                    stats["rule_chunks"] += 1
                elif category == ChunkCategory.CONDITION:
                    stats["condition_chunks"] += 1

        return passed, stats
