import json
import logging
import os
import re
import time
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个专业的中国民航法规知识图谱抽取专家。

【绝对规则 - 必须遵守】
1. 你只能输出 JSON 格式，不能输出任何其他内容
2. 不要输出解释、说明、Markdown、代码块标记、自然语言
3. 如果无法抽取或文本不适合抽取，返回 should_extract=false
4. 所有字段必须存在，即使为空字符串或空数组

【抽取范围】
只抽取以下类型：
- 定义类：包含"是指""定义为""术语的含义"等句式
- 规则类：包含"应当/不得/可以/负责/必须/禁止/仅允许"
- 条件类：包含"在...情况下""除...外""当...时""只有...方可"
- 阈值类：包含数值+单位（如300米、5个工作日）

【跳过以下类型】
- 只有条号、目录、页码残留
- 附表、申请表、备案表、附图、示意图
- 生效/废止/修订历史
- 纯引用句（"见附件""见表""见图"）

【严格 JSON 输出格式】
你必须严格按照以下模板输出，不要新增任何字段：

{
  "should_extract": true,
  "reason": "",
  "definitions": [
    {
      "term_name": "术语名",
      "definition_text": "定义内容",
      "category": "airspace|flight_rule|atc_service|organization|facility|aircraft|uav|procedure|license|generic",
      "confidence": 0.9,
      "evidence_text": "原文证据"
    }
  ],
  "rules": [
    {
      "rule_type": "obligation|prohibition|permission|responsibility|requirement",
      "modality": "应当|不得|可以|负责|必须|禁止|仅允许",
      "subject": "主体",
      "action": "动作",
      "object": "对象(可为空)",
      "confidence": 0.9,
      "evidence_text": "原文证据"
    }
  ],
  "conditions": [
    {
      "condition_type": "scope|prerequisite|trigger|exception|temporal|spatial|operational",
      "text": "条件文本",
      "confidence": 0.9,
      "evidence_text": "原文证据"
    }
  ],
  "constraints": [
    {
      "text": "约束文本",
      "comparator": ">|>=|<|<=|=|range|none",
      "value": "数值",
      "unit": "单位",
      "confidence": 0.9,
      "evidence_text": "原文证据"
    }
  ],
  "references": [
    {
      "ref_type": "law|regulation|annex|article",
      "ref_text": "引用文本",
      "confidence": 0.9,
      "evidence_text": "原文证据"
    }
  ]
}

【重要提醒】
- 输出只能是一个完整的 JSON 对象
- 数组中没有内容时返回 []
- 字符串没有内容时返回 ""
- confidence 范围 0.0-1.0
"""

USER_PROMPT_TEMPLATE = """请对以下条文进行知识图谱抽取。直接输出JSON，不要任何解释。

文档信息:
chunk_id: {chunk_id}
doc_title: {doc_title}
article_no: {article_no}

原文:
{text}

输出JSON:"""


def safe_parse_json(raw: str) -> tuple[Optional[Dict], str]:
    if not raw:
        return None, "Empty response"

    raw = raw.strip()
    original = raw

    try:
        result = json.loads(raw)
        return result, "ok"
    except json.JSONDecodeError:
        pass

    if raw.startswith("```"):
        first_newline = raw.find("\n")
        last_backtick = raw.rfind("```")
        if last_backtick > first_newline:
            raw = raw[first_newline + 1:last_backtick].strip()

    json_start = raw.find("{")
    json_end = raw.rfind("}")
    if json_start >= 0 and json_end > json_start:
        extracted = raw[json_start:json_end + 1]
        try:
            result = json.loads(extracted)
            return result, "extracted_from_response"
        except json.JSONDecodeError:
            pass

    fixed = raw.replace("'", '"')
    fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
    fixed = re.sub(r'([{[])\s*:', r'\1:', fixed)
    try:
        result = json.loads(fixed)
        return result, "fixed_json"
    except json.JSONDecodeError:
        pass

    logger.debug(f"Failed to parse JSON. Raw (first 500 chars): {original[:500]}...")
    return None, f"parse_failed: {original[:100]}"


class LLMProvider:
    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "",
        temperature: float = 0.05,
        max_tokens: int = 800,
        timeout: int = 30,
    ):
        # 从环境变量读取配置
        self.api_key = api_key or os.environ.get("SILICONFLOW_API_KEY", "")
        self.base_url = (base_url or os.environ.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")).rstrip("/")
        self.model = model or os.environ.get("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V3")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._enabled = bool(self.api_key)
        self._call_count = 0
        self._success_count = 0
        self._fail_count = 0
        if not self._enabled:
            logger.warning("LLM provider: No API key configured.")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def configure(self, api_key: str = "", model: str = "", base_url: str = "") -> None:
        if api_key:
            self.api_key = api_key
            self._enabled = True
        if model:
            self.model = model
        if base_url:
            self.base_url = base_url.rstrip("/")

    def extract_chunk(
        self,
        chunk_id: str,
        text: str,
        category: str,
        metadata: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not self._enabled:
            return None

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

        try:
            start_time = time.time()
            result_raw = self._call_api(SYSTEM_PROMPT, user_prompt)
            latency_ms = (time.time() - start_time) * 1000
            
            parsed, parse_status = safe_parse_json(result_raw)
            
            self._call_count += 1
            if parsed:
                self._success_count += 1
                logger.info(f"[{chunk_id}] OK ({latency_ms:.0f}ms, parse={parse_status})")
                return parsed
            else:
                self._fail_count += 1
                logger.warning(f"[{chunk_id}] PARSE_FAIL ({latency_ms:.0f}ms, reason={parse_status})")
                if len(result_raw) > 200:
                    logger.warning(f"  Raw response preview: {result_raw[:200]}...")
                return None
        except Exception as e:
            self._fail_count += 1
            logger.error(f"[{chunk_id}] ERROR: {e}")
            return None

    def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        import requests

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

        start_time = time.time()
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        elapsed = time.time() - start_time
        
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        
        logger.debug(f"API call completed in {elapsed:.2f}s, response length: {len(content)}")
        return content

    def get_stats(self) -> Dict[str, int]:
        return {
            "total_calls": self._call_count,
            "success_count": self._success_count,
            "fail_count": self._fail_count,
            "success_rate": round(self._success_count / max(self._call_count, 1) * 100, 1),
        }
