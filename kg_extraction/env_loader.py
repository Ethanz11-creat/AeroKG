"""
统一的环境变量加载工具
从 .env 文件加载配置
"""

import os
from pathlib import Path
from dotenv import load_dotenv


def load_env_config():
    """从 .env 文件加载配置"""
    env_file = Path(__file__).parent.parent / ".env"
    
    if env_file.exists():
        load_dotenv(env_file)
        return True
    
    return False


def get_neo4j_config():
    """获取 Neo4j 配置"""
    return {
        "uri": os.environ.get("NEO4J_URI", ""),
        "username": os.environ.get("NEO4J_USERNAME", ""),
        "password": os.environ.get("NEO4J_PASSWORD", ""),
        "database": os.environ.get("NEO4J_DATABASE", ""),
    }


def validate_neo4j_config():
    """验证 Neo4j 配置是否完整"""
    config = get_neo4j_config()
    
    if not all(config.values()):
        print("❌ Neo4j 配置不完整！")
        print("\n请在项目根目录创建 .env 文件并添加以下配置：")
        print("NEO4J_URI=neo4j+s://...")
        print("NEO4J_USERNAME=...")
        print("NEO4J_PASSWORD=...")
        print("NEO4J_DATABASE=...")
        return False
    
    return True


if __name__ == "__main__":
    print("\n" + "="*60)
    print("环境变量配置检查")
    print("="*60)
    
    if load_env_config():
        print("\n✅ 成功加载 .env 文件")
    else:
        print("\n⚠️  未找到 .env 文件")
    
    print("\n📋 配置信息:")
    print(f"  SILICONFLOW_API_KEY: {'已配置' if os.environ.get('SILICONFLOW_API_KEY') else '未配置'}")
    print(f"  NEO4J_URI: {os.environ.get('NEO4J_URI', '未配置')}")
    print(f"  NEO4J_USERNAME: {os.environ.get('NEO4J_USERNAME', '未配置')}")
    print(f"  NEO4J_PASSWORD: {'已配置' if os.environ.get('NEO4J_PASSWORD') else '未配置'}")
    print(f"  NEO4J_DATABASE: {os.environ.get('NEO4J_DATABASE', '未配置')}")
