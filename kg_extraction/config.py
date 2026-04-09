import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"✓ 加载配置文件: {env_file}")
else:
    print(f"⚠️  未找到配置文件: {env_file}")

# ============================================
# SiliconFlow API 配置
# ============================================
SILICONFLOW_API_KEY = os.environ.get("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.environ.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
SILICONFLOW_MODEL = os.environ.get("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V3")

# ============================================
# Neo4j 配置
# ============================================
NEO4J_URI = os.environ.get("NEO4J_URI", "")
NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME", "")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "")

# ============================================
# LLM 参数配置
# ============================================
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.05"))
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "800"))
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "45"))
LLM_DELAY_SECONDS = float(os.environ.get("LLM_DELAY_SECONDS", "0.2"))
LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "1"))
LLM_MAX_CONCURRENCY = int(os.environ.get("LLM_MAX_CONCURRENCY", "3"))

# ============================================
# 抽取配置
# ============================================
EXTRACTION_MODE = "llm"
FALLBACK_TO_RULES = True
MIN_CHUNK_LENGTH = 15
MAX_CHUNK_LENGTH = 3000
OUTPUT_DIR = "kg_output"


def get_api_key() -> str:
    """获取 API Key"""
    if not SILICONFLOW_API_KEY:
        raise ValueError(
            "未配置 SILICONFLOW_API_KEY！\n"
            "请在项目根目录创建 .env 文件并添加：\n"
            "SILICONFLOW_API_KEY=your_api_key_here"
        )
    return SILICONFLOW_API_KEY


def get_neo4j_config() -> dict:
    """获取 Neo4j 配置"""
    if not all([NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE]):
        raise ValueError(
            "未配置 Neo4j 连接信息！\n"
            "请在项目根目录创建 .env 文件并添加：\n"
            "NEO4J_URI=neo4j+s://...\n"
            "NEO4J_USERNAME=...\n"
            "NEO4J_PASSWORD=...\n"
            "NEO4J_DATABASE=..."
        )
    return {
        "uri": NEO4J_URI,
        "username": NEO4J_USERNAME,
        "password": NEO4J_PASSWORD,
        "database": NEO4J_DATABASE,
    }


def get_config():
    """获取完整配置"""
    return Config(
        api_key=get_api_key(),
        base_url=SILICONFLOW_BASE_URL,
        model=SILICONFLOW_MODEL,
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
        timeout=LLM_TIMEOUT,
        delay_seconds=LLM_DELAY_SECONDS,
        extraction_mode=EXTRACTION_MODE,
        fallback_to_rules=FALLBACK_TO_RULES,
    )


@dataclass
class Config:
    api_key: str
    base_url: str
    model: str
    temperature: float
    max_tokens: int
    timeout: int
    delay_seconds: float
    extraction_mode: str
    fallback_to_rules: bool


# 验证配置
if __name__ == "__main__":
    print("\n" + "="*60)
    print("配置验证")
    print("="*60)
    
    print("\n📋 SiliconFlow API:")
    print(f"  API Key: {'已配置' if SILICONFLOW_API_KEY else '未配置'}")
    print(f"  Base URL: {SILICONFLOW_BASE_URL}")
    print(f"  Model: {SILICONFLOW_MODEL}")
    
    print("\n📋 Neo4j:")
    print(f"  URI: {NEO4J_URI if NEO4J_URI else '未配置'}")
    print(f"  Username: {NEO4J_USERNAME if NEO4J_USERNAME else '未配置'}")
    print(f"  Password: {'已配置' if NEO4J_PASSWORD else '未配置'}")
    print(f"  Database: {NEO4J_DATABASE if NEO4J_DATABASE else '未配置'}")
    
    print("\n📋 LLM 参数:")
    print(f"  Temperature: {LLM_TEMPERATURE}")
    print(f"  Max Tokens: {LLM_MAX_TOKENS}")
    print(f"  Timeout: {LLM_TIMEOUT}s")
    print(f"  Max Concurrency: {LLM_MAX_CONCURRENCY}")
    
    if not SILICONFLOW_API_KEY:
        print("\n⚠️  警告: 未配置 SILICONFLOW_API_KEY")
    
    if not all([NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE]):
        print("\n⚠️  警告: Neo4j 配置不完整")
