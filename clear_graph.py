"""
清空 Neo4j Aura 图谱数据库
删除所有节点和关系
"""

import os
import sys
from pathlib import Path
from neo4j import GraphDatabase

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from kg_extraction.env_loader import load_env_config, get_neo4j_config, validate_neo4j_config

def clear_database(driver, database):
    """清空数据库"""
    print("\n🗑️  开始清空图谱...")
    
    with driver.session(database=database) as session:
        # 1. 统计现有数据
        print("\n📊 当前数据统计:")
        result = session.run("MATCH (n) RETURN count(n) as count")
        node_count = result.single()['count']
        print(f"  节点总数: {node_count}")
        
        result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
        rel_count = result.single()['count']
        print(f"  关系总数: {rel_count}")
        
        if node_count == 0:
            print("\n✅ 图谱已经是空的，无需清空")
            return
        
        # 2. 确认清空
        print(f"\n⚠️  即将删除 {node_count} 个节点和 {rel_count} 条关系")
        confirm = input("确认清空? (yes/no): ").strip().lower()
        
        if confirm != 'yes':
            print("❌ 已取消清空操作")
            return False
        
        # 3. 删除所有关系
        print("\n删除所有关系...")
        result = session.run("MATCH ()-[r]->() DELETE r RETURN count(r) as deleted")
        deleted_rels = result.single()['deleted']
        print(f"  ✓ 删除关系: {deleted_rels}")
        
        # 4. 删除所有节点
        print("删除所有节点...")
        result = session.run("MATCH (n) DELETE n RETURN count(n) as deleted")
        deleted_nodes = result.single()['deleted']
        print(f"  ✓ 删除节点: {deleted_nodes}")
        
        # 5. 验证清空结果
        result = session.run("MATCH (n) RETURN count(n) as count")
        final_count = result.single()['count']
        
        if final_count == 0:
            print("\n✅ 图谱已完全清空!")
            return True
        else:
            print(f"\n⚠️  警告: 还有 {final_count} 个节点未删除")
            return False

def main():
    print("\n" + "="*60)
    print("Neo4j Aura 图谱清空工具")
    print("="*60)
    
    # 加载配置
    if not load_env_config():
        print("❌ 未找到配置文件 .env")
        print("\n请创建 .env 文件并配置以下信息:")
        print("NEO4J_URI=...")
        print("NEO4J_USERNAME=...")
        print("NEO4J_PASSWORD=...")
        print("NEO4J_DATABASE=...")
        return
    
    # 验证配置
    if not validate_neo4j_config():
        return
    
    # 获取配置
    config = get_neo4j_config()
    
    print(f"\n连接信息:")
    print(f"  URI: {config['uri']}")
    print(f"  用户名: {config['username']}")
    print(f"  数据库: {config['database']}")
    
    # 连接数据库
    print("\n连接数据库...")
    try:
        driver = GraphDatabase.driver(
            config['uri'], 
            auth=(config['username'], config['password'])
        )
        driver.verify_connectivity()
        print("✅ 连接成功!")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return
    
    try:
        # 清空数据库
        success = clear_database(driver, config['database'])
        
        if success:
            print("\n" + "="*60)
            print("✓ 清空完成!")
            print("="*60)
            print("\n现在可以运行导入脚本:")
            print("  python import_complete_graph.py")
    finally:
        driver.close()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已取消")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
