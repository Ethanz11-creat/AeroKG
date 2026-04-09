"""
Neo4j 图谱优化脚本
执行6个关键优化步骤
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


def step1_create_rule_fulltext_index(session):
    """Step 1: 创建 Rule fulltext index"""
    print("\n" + "="*60)
    print("Step 1: 创建 Rule fulltext index")
    print("="*60)
    
    try:
        # 检查索引是否已存在
        result = session.run("""
            SHOW INDEXES WHERE name = 'rule_evidence_fulltext'
        """)
        if list(result):
            print("  ✅ 索引已存在: rule_evidence_fulltext")
            return True
        
        # 创建索引
        session.run("""
            CREATE FULLTEXT INDEX rule_evidence_fulltext
            FOR (r:Rule) ON EACH [r.evidence_text]
        """)
        print("  ✅ 成功创建: rule_evidence_fulltext")
        return True
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        return False

def step2_create_article_nodes(session):
    """Step 2: 创建 Article 节点层"""
    print("\n" + "="*60)
    print("Step 2: 创建 Article 节点层")
    print("="*60)
    
    try:
        # 统计需要创建的Article数量
        result = session.run("""
            MATCH (r:Rule)
            WHERE NOT r.chunk_id CONTAINS 'merged'
            WITH r.chunk_id as chunk_id, count(r) as rule_count
            RETURN count(chunk_id) as article_count
        """)
        article_count = result.single()['article_count']
        print(f"  需要创建 {article_count} 个 Article 节点")
        
        # 创建Article节点
        result = session.run("""
            CALL {
                MATCH (r:Rule)
                WHERE NOT r.chunk_id CONTAINS 'merged'
                WITH r.chunk_id as art_chunk_id
                MERGE (a:Article {chunk_id: art_chunk_id})
                SET a.article_no = art_chunk_id
                RETURN count(a) as created
            }
            RETURN created
        """)
        created = result.single()['created']
        print(f"  ✅ 成功创建 {created} 个 Article 节点")
        return True
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        return False

def step3_fix_references_relations(session):
    """Step 3: 创建 Rule → REFERENCES 关系"""
    print("\n" + "="*60)
    print("Step 3: 创建 Rule → REFERENCES 关系")
    print("="*60)
    
    try:
        # 统计现有关系
        result = session.run("""
            MATCH (su:StructuralUnit)-[old:REFERENCES]->(ref:Reference)
            RETURN count(old) as old_count
        """)
        old_count = result.single()['old_count']
        print(f"  现有 StructuralUnit → REFERENCES 关系: {old_count} 条")
        
        # 创建新的 Rule → REFERENCES 关系
        result = session.run("""
            MATCH (su:StructuralUnit)-[:HAS_RULE]->(r:Rule),
                  (su)-[old:REFERENCES]->(ref:Reference)
            CREATE (r)-[:REFERENCES]->(ref)
            WITH old
            DELETE old
            RETURN count(old) as deleted
        """)
        deleted = result.single()['deleted']
        print(f"  ✅ 删除旧关系: {deleted} 条")
        
        # 验证新关系
        result = session.run("""
            MATCH (r:Rule)-[new:REFERENCES]->(ref:Reference)
            RETURN count(new) as new_count
        """)
        new_count = result.single()['new_count']
        print(f"  ✅ 创建新关系: {new_count} 条")
        return True
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        return False

def step4_mark_duplicate_rules(session):
    """Step 4: 去重/标记重复 Rules"""
    print("\n" + "="*60)
    print("Step 4: 去重/标记重复 Rules")
    print("="*60)
    
    try:
        # 统计重复的chunk_id
        result = session.run("""
            MATCH (r:Rule)
            WITH r.chunk_id as cid, count(r) as rule_count
            WHERE rule_count > 1
            RETURN count(cid) as duplicate_groups, sum(rule_count) as total_rules
        """)
        record = result.single()
        duplicate_groups = record['duplicate_groups']
        total_rules = record['total_rules']
        print(f"  发现 {duplicate_groups} 个重复组，共 {total_rules} 条规则")
        
        # 标记重复规则
        result = session.run("""
            MATCH (r:Rule)
            WITH r.chunk_id as cid, collect(r) as rules
            WHERE size(rules) > 1
            UNWIND range(0, size(rules)-1) as idx
            WITH rules[idx] as r, idx, cid
            SET r.is_duplicate = (idx > 0),
                r.duplicate_group = cid,
                r.duplicate_index = idx
            RETURN count(r) as marked
        """)
        marked = result.single()['marked']
        print(f"  ✅ 标记了 {marked} 条重复规则")
        
        # 统计主规则和重复规则
        result = session.run("""
            MATCH (r:Rule)
            WHERE r.is_duplicate IS NOT NULL
            RETURN 
                count(CASE WHEN r.is_duplicate = false THEN 1 END) as primary_count,
                count(CASE WHEN r.is_duplicate = true THEN 1 END) as duplicate_count
        """)
        record = result.single()
        print(f"  ✅ 主规则: {record['primary_count']} 条")
        print(f"  ✅ 重复规则: {record['duplicate_count']} 条")
        return True
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        return False

def step5_add_intra_document_field(session):
    """Step 5: 补充 is_intra_document 字段"""
    print("\n" + "="*60)
    print("Step 5: 补充 is_intra_document 字段")
    print("="*60)
    
    try:
        # 标记文内引用
        result = session.run("""
            MATCH (ref:Reference)
            WHERE ref.ref_text CONTAINS '本规则'
               OR (ref.ref_text CONTAINS '第' AND ref.ref_text CONTAINS '条')
            SET ref.is_intra_document = true,
                ref.normalized_ref_type = 'intra_document_reference'
            RETURN count(ref) as marked
        """)
        marked = result.single()['marked']
        print(f"  ✅ 标记了 {marked} 条文内引用")
        
        # 标记外部引用
        result = session.run("""
            MATCH (ref:Reference)
            WHERE NOT ref.is_intra_document = true
            SET ref.is_intra_document = false
            RETURN count(ref) as external
        """)
        external = result.single()['external']
        print(f"  ✅ 标记了 {external} 条外部引用")
        
        # 统计结果
        result = session.run("""
            MATCH (ref:Reference)
            RETURN 
                count(CASE WHEN ref.is_intra_document = true THEN 1 END) as intra_count,
                count(CASE WHEN ref.is_intra_document = false THEN 1 END) as external_count
        """)
        record = result.single()
        print(f"  ✅ 文内引用: {record['intra_count']} 条")
        print(f"  ✅ 外部引用: {record['external_count']} 条")
        return True
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        return False

def step6_create_rule_article_relations(session):
    """Step 6: 创建 Rule → Article 关系"""
    print("\n" + "="*60)
    print("Step 6: 创建 Rule → Article 关系")
    print("="*60)
    
    try:
        # 创建 DERIVED_FROM 关系
        result = session.run("""
            MATCH (r:Rule), (a:Article)
            WHERE r.chunk_id = a.chunk_id AND NOT r.chunk_id CONTAINS 'merged'
            MERGE (r)-[:DERIVED_FROM]->(a)
            RETURN count(*) as created
        """)
        created = result.single()['created']
        print(f"  ✅ 创建了 {created} 条 DERIVED_FROM 关系")
        
        # 验证关系
        result = session.run("""
            MATCH (r:Rule)-[rel:DERIVED_FROM]->(a:Article)
            RETURN count(rel) as total
        """)
        total = result.single()['total']
        print(f"  ✅ 总关系数: {total} 条")
        return True
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        return False

def verify_optimizations(session):
    """验证优化结果"""
    print("\n" + "="*60)
    print("验证优化结果")
    print("="*60)
    
    # 1. 验证全文索引
    print("\n📑 全文索引:")
    result = session.run("""
        SHOW INDEXES WHERE type = 'FULLTEXT'
    """)
    for idx in result:
        print(f"  {idx['name']}: {idx['labelsOrTypes']} - {idx['properties']}")
    
    # 2. 验证Article节点
    print("\n📊 Article节点统计:")
    result = session.run("""
        MATCH (a:Article)
        RETURN count(a) as count
    """)
    count = result.single()['count']
    print(f"  Article节点数: {count}")
    
    # 3. 验证REFERENCES关系
    print("\n🔗 REFERENCES关系统计:")
    result = session.run("""
        MATCH (r:Rule)-[rel:REFERENCES]->(ref:Reference)
        RETURN count(rel) as count
    """)
    count = result.single()['count']
    print(f"  Rule → REFERENCES: {count}")
    
    # 4. 验证重复标记
    print("\n🔄 重复规则统计:")
    result = session.run("""
        MATCH (r:Rule)
        WHERE r.is_duplicate IS NOT NULL
        RETURN 
            count(CASE WHEN r.is_duplicate = false THEN 1 END) as primary,
            count(CASE WHEN r.is_duplicate = true THEN 1 END) as duplicate
    """)
    record = result.single()
    print(f"  主规则: {record['primary']}")
    print(f"  重复规则: {record['duplicate']}")
    
    # 5. 验证is_intra_document
    print("\n📖 引用类型统计:")
    result = session.run("""
        MATCH (ref:Reference)
        RETURN 
            count(CASE WHEN ref.is_intra_document = true THEN 1 END) as intra,
            count(CASE WHEN ref.is_intra_document = false THEN 1 END) as external
    """)
    record = result.single()
    print(f"  文内引用: {record['intra']}")
    print(f"  外部引用: {record['external']}")
    
    # 6. 验证DERIVED_FROM关系
    print("\n🔗 DERIVED_FROM关系统计:")
    result = session.run("""
        MATCH (r:Rule)-[rel:DERIVED_FROM]->(a:Article)
        RETURN count(rel) as count
    """)
    count = result.single()['count']
    print(f"  Rule → DERIVED_FROM → Article: {count}")

def main():
    print("\n" + "="*60)
    print("Neo4j 图谱优化脚本")
    print("="*60)
    
    # 加载配置
    if not load_config():
        print("❌ 未找到配置文件 .env")
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
            results.append(("Step 1: Rule fulltext index", step1_create_rule_fulltext_index(session)))
            results.append(("Step 2: Article 节点层", step2_create_article_nodes(session)))
            results.append(("Step 3: REFERENCES 关系", step3_fix_references_relations(session)))
            results.append(("Step 4: 标记重复 Rules", step4_mark_duplicate_rules(session)))
            results.append(("Step 5: is_intra_document", step5_add_intra_document_field(session)))
            results.append(("Step 6: Rule → Article 关系", step6_create_rule_article_relations(session)))
            
            # 验证结果
            verify_optimizations(session)
            
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
