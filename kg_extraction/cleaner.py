import re
import logging
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

PAGE_NUM_PATTERN = re.compile(r"^[\s]*[-—－]\s*\d+\s*[-—－]\s*$")
TABLE_KEYWORDS = {"附表", "备案表", "申请表", "附图", "示意图", "附录表"}
APPENDIX_PATTERNS = [
    re.compile(r"^(本规则|本条例|本办法|本规定).*(自.*起|施行|生效)"),
    re.compile(r"^(第[一二三四五六七八九十百千\d]+条).*([废止]|修改前)"),
    re.compile(r"^(附件|附则|附录)\b"),
]


class TextCleaner:
    def clean(self, chunk: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        text = chunk.get("text", "")
        metadata = chunk.get("metadata", {})
        flags = {}

        text, flags = self._remove_page_numbers(text, flags)
        text = self._fix_pdf_line_breaks(text)
        text = self._normalize_whitespace(text)
        text, flags = self._check_length(text, flags)
        flags = self._check_table_chunk(text, flags)
        flags = self._check_appendix_block(text, flags)
        flags = self._check_article_consistency(text, metadata, flags)

        chunk["text"] = text
        return chunk, flags

    def _remove_page_numbers(self, text: str, flags: Dict) -> Tuple[str, Dict]:
        lines = text.split("\n")
        cleaned = [l for l in lines if not PAGE_NUM_PATTERN.match(l.strip())]
        result = "\n".join(cleaned)
        if len(cleaned) < len(lines):
            flags["page_number_removed"] = True
        return result, flags

    def _fix_pdf_line_breaks(self, text: str) -> str:
        text = re.sub(r"(\w)\n(\w)", r"\1\2", text)
        text = re.sub(r"(\w)\n(\w)", r"\1\2", text)
        return text

    def _normalize_whitespace(self, text: str) -> str:
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()
        return text

    def _check_length(self, text: str, flags: Dict) -> Tuple[str, Dict]:
        char_count = len(text.replace(" ", "").replace("\n", ""))
        flags["char_count"] = char_count
        if char_count < 15:
            flags["too_short"] = True
        elif char_count > 3000:
            flags["review_required"] = True
        return text, flags

    def _check_table_chunk(self, text: str, flags: Dict) -> Dict:
        for kw in TABLE_KEYWORDS:
            if kw in text:
                flags["is_table_or_figure"] = True
                break
        return flags

    def _check_appendix_block(self, text: str, flags: Dict) -> Dict:
        for pat in APPENDIX_PATTERNS:
            if pat.search(text):
                flags["is_appendix_block"] = True
                break
        return flags

    def _check_article_consistency(self, text: str, metadata: Dict, flags: Dict) -> Dict:
        article_no = metadata.get("article_no", "")
        if article_no and not text.startswith(article_no):
            stripped = text.lstrip()
            if article_no[:2] in ["第十", "第一"] or any(
                stripped.startswith(f"第{c}") for c in "一二三四五六七八九十"
            ):
                pass
            else:
                flags["suspicious_article_match"] = True
        return flags
