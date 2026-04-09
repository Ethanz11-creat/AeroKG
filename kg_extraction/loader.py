import json
import logging
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class ChunkLoader:
    def __init__(self, input_path: str):
        self.input_path = Path(input_path)

    def load(self) -> List[Dict[str, Any]]:
        if not self.input_path.exists():
            raise FileNotFoundError(f"Input file not found: {self.input_path}")
        with open(self.input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("chunks.json must be a JSON array")
        logger.info(f"Loaded {len(data)} chunks from {self.input_path}")
        return data

    @staticmethod
    def validate_chunk(chunk: Dict[str, Any]) -> bool:
        required_keys = {"id", "text", "metadata"}
        if not required_keys.issubset(chunk.keys()):
            return False
        meta_required = {"doc_title", "article_no"}
        return meta_required.issubset(chunk["metadata"].keys())
