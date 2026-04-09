"""
补充 Article 节点优化
1. 补充 Article.text（从 chunks.json 同步）
2. 为 merged chunk Rules 创建虚拟 Article 节点
"""

import os
import sys
from pathlib import Path
from neo4j import GraphDatabase

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from kg_extraction.env_loader import load_env_config, get_neo4j_config, validate_neo4j_config


import json
from typing import Dict, List, Any

def load_config():
    """加载配置"""
    if not load_env_config():
        print("❌ 未找到配置文件 .env")
        return None
    
    if not validate_neo4j_config():
        return None
    
    return get_neo4j_config()


def load_chunks_data() -> Dict[str, Dict[str, Any]]:
    """加载 chunks.json 数据"""
    chunks_file = Path('chunks.json')
    
    if not chunks_file.exists():
        print(f"❌ 未找到 chunks.json 文件")
        return {}
    
    print(f"✓ 加载 chunks.json 文件...")
    with open(chunks_file, 'r', encoding='utf-8') as f:
        chunks = json.load(f)
    
    # 转换为字典，key 为 chunk_id
    chunks_dict = {}
    for chunk in chunks:
        chunk_id = chunk.get('id', '')
        if chunk_id:
            chunks_dict[chunk_id] = {
                'text': chunk.get('text', ''),
                'metadata': chunk.get('metadata', {})
            }
    
    print(f"  加载了 {len(chunks_dict)} 个 chunks")
    return chunks_dict

def step1_populate_article_text(session, chunks_dict: Dict[str, Dict[str, Any]]):
    """Step 1: 补充 Article.text"""
    print("\n" + "="*60)
    print("Step 1: 补充 Article.text")
    print("="*60)
    
    # 获取所有 Article 节点
    result = session.run("""
        MATCH (a:Article)
        WHERE NOT a.chunk_id CONTAINS 'merged'
        RETURN a.chunk_id as chunk_id
    """)
    
    articles = [record['chunk_id'] for record in result]
    print(f"  找到 {len(articles)} 个 Article 节点")
    
    # 更新 Article.text
    updated_count = 0
    not_found_count = 0
    
    for chunk_id in articles:
        if chunk_id in chunks_dict:
            text = chunks_dict[chunk_id]['text']
            metadata = chunks_dict[chunk_id]['metadata']
            
            # 更新 Article 节点
            session.run("""
                MATCH (a:Article {chunk_id: $chunk_id})
                SET a.text = $text,
                    a.doc_title = $doc_title,
                    a.article_no = $article_no
            """, chunk_id=chunk_id, text=text, 
                 doc_title=metadata.get('doc_title', ''),
                 article_no=metadata.get('article_no', ''))
            
            updated_count += 1
        else:
            not_found_count += 1
    
    print(f"  ✅ 更新了 {updated_count} 个 Article 节点")
    if not_found_count > 0:
        print(f"  ⚠️  {not_found_count} 个 chunk_id 在 chunks.json 中未找到")
    
    return True

def step2_create_merged_article_nodes(session):
    """Step 2: 为 merged chunk Rules 创建虚拟 Article 节点"""
    print("\n" + "="*60)
    print("Step 2: 创建虚拟 Article 节点")
    print("="*60)
    
    # 查找所有 merged chunk 的 Rule
    result = session.run("""
        MATCH (r:Rule)
        WHERE r.chunk_id CONTAINS 'merged'
        RETURN DISTINCT r.chunk_id as chunk_id
    """)
    
    merged_chunks = [record['chunk_id'] for record in result]
    print(f"  找到 {len(merged_chunks)} 个 merged chunk")
    
    # 为每个 merged chunk 创建虚拟 Article 节点
    created_count = 0
    
    for chunk_id in merged_chunks:
        # 创建虚拟 Article 节点
        session.run("""
            MERGE (a:Article {chunk_id: $chunk_id})
            SET a.is_virtual = true,
                a.article_no = 'merged',
                a.text = 'Virtual article for merged chunks'
        """, chunk_id=chunk_id)
        
        # 创建 DERIVED_FROM 关系
        session.run("""
            MATCH (r:Rule {chunk_id: $chunk_id})
            MATCH (a:Article {chunk_id: $chunk_id})
            MERGE (r)-[:DERIVED_FROM]->(a)
        """, chunk_id=chunk_id)
        
        created_count += 1
    
    print(f"  ✅ 创建了 {created_count} 个虚拟 Article 节点")
    
    # 验证所有 Rule 都有 DERIVED_FROM 关系
    result = session.run("""
        MATCH (r:Rule)
        WHERE NOT (r)-[:DERIVED_FROM]->(:Article)
        RETURN count(r) as count
    """)
    
    orphan_count = result.single()['count']
    if orphan_count > 0:
        print(f"  ⚠️  还有 {orphan_count} 条 Rule 没有 DERIVED_FROM 关系")
    else:
        print(f"  ✅ 所有 Rule 都有 DERIVED_FROM 关系")
    
    return True

def verify_article_optimization(session):
    """验证 Article 优化结果"""
    print("\n" + "="*60)
    print("验证 Article 优化结果")
    print("="*60)
    
    # 1. Article 节点统计
    print("\n📊 Article 节点统计:")
    result = session.run("""
        MATCH (a:Article)
        RETURN 
            count(a) as total,
            count(CASE WHEN a.text IS NOT NULL AND a.text <> '' THEN 1 END) as with_text,
            count(CASE WHEN a.is_virtual = true THEN 1 END) as virtual_count
    """)
    record = result.single()
    print(f"  Article 总数: {record['total']}")
    print(f"  有文本的 Article: {record['with_text']}")
    print(f"  虚拟 Article: {record['virtual_count']}")
    
    # 2. DERIVED_FROM 关系统计
    print("\n🔗 DERIVED_FROM 关系统计:")
    result = session.run("""
        MATCH (r:Rule)-[:DERIVED_FROM]->(a:Article)
        RETURN count(r) as count
    """)
    derived_count = result.single()['count']
    
    result = session.run("MATCH (r:Rule) RETURN count(r) as count")
    total_rules = result.single()['count']
    
    print(f"  有 DERIVED_FROM 关系的 Rule: {derived_count}/{total_rules}")
    
    # 3. Article 文本示例
    print("\n📝 Article 文本示例:")
    result = session.run("""
        MATCH (a:Article)
        WHERE a.text IS NOT NULL AND a.text <> ''
        RETURN a.chunk_id, a.article_no, a.text
        LIMIT 3
    """)
    for i, record in enumerate(result, 1):
        print(f"  {i}. {record['a.chunk_id']} ({record['a.article_no']})")
        print(f"     文本: {record['a.text'][:80]}...")
    
    # 4. 虚拟 Article 示例
    print("\n🔗 虚拟 Article 示例:")
    result = session.run("""
        MATCH (a:Article)
        WHERE a.is_virtual = true
        RETURN a.chunk_id, count{(a)<-[:DERIVED_FROM]-(:Rule)} as rule_count
        ORDER BY rule_count DESC
        LIMIT 3
    """)
    for i, record in enumerate(result, 1):
        print(f"  {i}. {record['a.chunk_id'][:50]}... ({record['rule_count']} 条规则)")

def show_query_examples(session):
    """展示查询示例"""
    print("\n" + "="*60)
    print("💡 查询示例")
    print("="*60)
    
    # 示例: 通过全文检索查找规则并获取 Article 信息
    print("\n  示例: 全文检索 '空域' 并获取 Article 信息")
    result = session.run("""
        CALL db.index.fulltext.queryNodes('rule_evidence_fulltext', '空域')
        YIELD node, score
        MATCH (node)-[:DERIVED_FROM]->(a:Article)
        RETURN node.subject, a.article_no, a.text, score
        ORDER BY score DESC
        LIMIT 1
    """)
    record = result.single()
    if record:
        print(f"    规则主体: {record['node.subject'][:40]}...")
        print(f"    所属条款: {record['a.article_no']}")
        print(f"    原文: {record['a.text'][:60]}...")
        print(f"    评分: {record['score']:.2f}")

def main():
    print("\n" + "="*60)
    print("Article 节点优化脚本")
    print("="*60)
    
    # 加载配置
    if not load_config():
        print("❌ 未找到配置文件 .env")
        return
    
    # 加载 chunks 数据
    chunks_dict = load_chunks_data()
    if not chunks_dict:
        print("❌ 无法加载 chunks 数据")
        return
    
    # 获取配置
    uri = os.environ.get('NEO4J_URI')
    username = os.environ.get('NEO4J_USERNAME')
    password = os.environ.get('NEO4J_PASSWORD')
    database = os.environ.get('NEO4J_DATABASE')
    
    if not all([uri, username, password, database]):
        print("❌ 配置文件缺少必要信息")
        return
    
    print(f"\n连接信息:")
    print(f"  URI: {uri}")
    print(f"  数据库: {database}")
    
    # 连接数据库
    print("\n连接数据库...")
    try:
        driver = GraphDatabase.driver(uri, auth=(username, password))
        driver.verify_connectivity()
        print("✅ 连接成功!")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return
    
    try:
        with driver.session(database=database) as session:
            # 执行优化步骤
            print("\n" + "="*60)
            print("开始执行优化步骤")
            print("="*60)
            
            results = []
            results.append(("Step 1: 补充 Article.text", step1_populate_article_text(session, chunks_dict)))
            results.append(("Step 2: 创建虚拟 Article 节点", step2_create_merged_article_nodes(session)))
            
            # 验证结果
            verify_article_optimization(session)
            
            # 展示查询示例
            show_query_examples(session)
            
            # 打印总结
            print("\n" + "="*60)
            print("优化完成总结")
            print("="*60)
            for step, success in results:
                status = "✅ 成功" if success else "❌ 失败"
                print(f"  {step}: {status}")
            
            success_count = sum(1 for _, s in results if s)
            print(f"\n总计: {success_count}/{len(results)} 步骤成功")
            
    finally:
        driver.close()

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
