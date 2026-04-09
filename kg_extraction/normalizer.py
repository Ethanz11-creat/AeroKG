import re
import logging
from typing import Dict, Optional, List, Tuple

logger = logging.getLogger(__name__)

ALIAS_MAP = {
    "中国民用航空局": ["民航局"],
    "民航地区管理局": ["地区管理局"],
    "通信导航监视": ["CNS"],
    "民用航空": ["民航"],
}

FULLWIDTH_MAP = str.maketrans(
    "０１２３４５６７８９（）【】《》，。：；""''！？、",
    "0123456789()[]《》,.:;\"'!?、",
)


class Normalizer:
    def __init__(self):
        self.alias_map = ALIAS_MAP
        self._build_reverse_alias()

    def _build_reverse_alias(self):
        self._reverse_alias = {}
        for full_name, aliases in self.alias_map.items():
            self._reverse_alias[full_name] = full_name
            for alias in aliases:
                self._reverse_alias[alias] = full_name

    def normalize_text(self, text: str) -> str:
        text = self._to_halfwidth(text)
        text = self._normalize_spaces(text)
        return text

    def normalize_entity(self, name: str) -> Tuple[str, str]:
        normalized = name.strip()
        normalized = self._to_halfwidth(normalized)
        normalized = self._remove_parenthetical_abbreviation(normalized)
        canonical = self._resolve_alias(normalized)
        return normalized, canonical

    def normalize_subject(self, subject: str) -> str:
        _, canonical = self.normalize_entity(subject)
        return canonical if canonical else subject

    def _to_halfwidth(self, text: str) -> str:
        return text.translate(FULLWIDTH_MAP)

    def _normalize_spaces(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def _remove_parenthetical_abbreviation(self, text: str) -> str:
        text = re.sub(r"[（(][^）)]*[）)]", "", text)
        text = re.sub(r"[「」""''][^「」""'']*[「」""'']", "", text)
        return text.strip()

    def _resolve_alias(self, name: str) -> Optional[str]:
        for key, canonical in self._reverse_alias.items():
            if key in name or name in key:
                return canonical
        return None

    @staticmethod
    def extract_term_from_definition(text: str, match_pos: int) -> Optional[str]:
        before = text[:match_pos]
        term_patterns = [
            re.compile(r'[""「」]([^""「」]+?)[""「」]\s*(?:是指|指|定义为)\s*$'),
            re.compile(r"([^\s，。：;]{2,15})(?:是指|指|定义为|的含义(?:是)?)\s*$"),
        ]
        for pat in term_patterns:
            m = pat.search(before)
            if m:
                return m.group(1).strip()
        return None

    @staticmethod
    def parse_rule_components(text: str, modality_keyword: str, position: int) -> Dict:
        before = text[:position].strip()
        after = text[position + len(modality_keyword):].strip()
        subject = ""
        action_obj = ""

        sentences_before = re.split(r'[，,。；;]', before)
        if sentences_before:
            last_sentence = sentences_before[-1].strip()
            subject_candidates = re.findall(r'[^\s，。；:：]{2,20}', last_sentence)
            if subject_candidates:
                subject = subject_candidates[-1]

        action_obj = after[:200] if after else ""

        obj = ""
        obj_markers = ["对", "向", "将", "把", "由"]
        for marker in obj_markers:
            idx = action_obj.find(marker)
            if idx >= 0:
                remaining = action_obj[idx + len(marker):]
                end_idx = min(len(remaining), 100)
                for sep in ["。", "；", "，"]:
                    si = remaining.find(sep)
                    if 5 < si < end_idx:
                        end_idx = si
                        break
                obj = remaining[:end_idx].strip()
                break

        action = action_obj[:len(action_obj) - len(obj)] if obj else action_obj
        action = action.rstrip("对向将把由")

        return {
            "subject": subject,
            "action": action.strip(),
            "object": obj,
        }
