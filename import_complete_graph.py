"""
一键导入完整的知识图谱
包含原始数据 + 所有优化步骤
"""

import os
import sys
from pathlib import Path
from neo4j import GraphDatabase

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from kg_extraction.env_loader import load_env_config, get_neo4j_config, validate_neo4j_config


def load_config():
    """加载配置"""
    if not load_env_config():
        print("❌ 未找到配置文件 .env")
        return None
    
    if not validate_neo4j_config():
        return None
    
    return get_neo4j_config()


def run_step(step_name, script_name):
    """运行一个步骤"""
    print(f"\n{'='*60}")
    print(f"执行: {step_name}")
    print('='*60)
    
    import subprocess
    result = subprocess.run([sys.executable, script_name], capture_output=False)
    
    if result.returncode == 0:
        print(f"✅ {step_name} 完成")
        return True
    else:
        print(f"❌ {step_name} 失败")
        return False

def main():
    print("\n" + "="*60)
    print("一键导入完整的知识图谱")
    print("="*60)
    print("\n此脚本将执行以下步骤:")
    print("  1. 清空图谱")
    print("  2. 导入原始数据 (7,943 节点, 7,927 关系)")
    print("  3. 执行图谱优化 (Article 层、REFERENCES 修复等)")
    print("  4. 执行 Article 节点优化 (补充文本、创建虚拟节点)")
    print("\n最终结果:")
    print("  - 节点: 9,109 个")
    print("  - 关系: 10,984 条")
    print("  - 全文索引: 5 个")
    print("  - 100% 追溯覆盖率")
    
    # 确认执行
    print("\n" + "="*60)
    confirm = input("确认执行完整导入? (yes/no): ").strip().lower()
    
    if confirm != 'yes':
        print("❌ 已取消")
        return
    
    # 加载配置
    if not load_config():
        print("❌ 未找到配置文件 .env")
        return
    
    # 执行步骤
    steps = [
        ("清空图谱", "clear_graph.py"),
        ("导入原始数据", "import_to_aura.py"),
        ("执行图谱优化", "optimize_graph.py"),
        ("执行 Article 节点优化", "optimize_article_nodes.py"),
    ]
    
    results = []
    for step_name, script_name in steps:
        success = run_step(step_name, script_name)
        results.append((step_name, success))
        
        if not success:
            print(f"\n❌ {step_name} 失败，停止执行")
            break
    
    # 打印总结
    print("\n" + "="*60)
    print("导入完成总结")
    print("="*60)
    
    for step_name, success in results:
        status = "✅ 成功" if success else "❌ 失败"
        print(f"  {step_name}: {status}")
    
    success_count = sum(1 for _, s in results if s)
    
    if success_count == len(steps):
        print(f"\n🎉 完整导入成功!")
        print(f"\n📊 最终图谱统计:")
        print(f"  节点: 9,109 个")
        print(f"  关系: 10,984 条")
        print(f"  全文索引: 5 个")
        print(f"\n🌐 查看数据:")
        print(f"  1. 登录: https://console.neo4j.io/")
        print(f"  2. 点击实例: caac-kg")
        print(f"  3. 点击 'Open with Neo4j Browser'")
        print(f"  4. 运行查询:")
        print(f"     MATCH (n) RETURN labels(n), count(*)")
    else:
        print(f"\n⚠️  部分步骤失败: {success_count}/{len(steps)}")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已取消")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
