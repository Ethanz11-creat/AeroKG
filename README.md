# 民航规章知识图谱 (CAAC Regulations Knowledge Graph)

## 📖 项目概述

本项目构建了一个基于中国民用航空规章的知识图谱，通过大语言模型（LLM）从民航规章文档中自动抽取结构化知识，形成可查询、可推理的知识网络。

### 核心价值

- 📚 **结构化知识**：将非结构化的规章文本转化为结构化图谱
- 🔍 **智能查询**：支持复杂的语义查询和关系推理
- 🎯 **合规检查**：快速定位相关规章条款
- 🔗 **关联分析**：发现规章之间的隐含关系
- 📊 **可视化展示**：直观展示规章体系结构

### 项目规模

- **数据规模**：16部民航规章
- **节点数量**：9,109个
- **关系数量**：10,984条
- **技术栈**：Python + LLM (DeepSeek-V3) + Neo4j Aura

---

## 🗂️ 项目结构

```
AeroKG/
├── kg_extraction/          # 知识抽取核心代码
│   ├── main.py            # 主入口
│   ├── extractor.py       # 抽取器
│   ├── llm_provider.py    # LLM接口
│   ├── async_extractor.py # 异步抽取器
│   ├── cleaner.py         # 文本清洗
│   ├── classifier.py      # 文本分类
│   ├── normalizer.py      # 标准化处理
│   ├── validator.py       # 质量验证
│   ├── exporter.py        # 结果导出
│   ├── config.py          # 配置管理 ⭐
│   └── env_loader.py      # 环境变量加载器 ⭐
│
├── kg_output/             # 抽取结果数据
│   ├── nodes_*.json      # 各类节点数据
│   ├── edges.json        # 关系数据
│   └── extraction_report.json
│
├── chunks.json            # 原始文本数据
├── .env                   # 环境变量配置 ⭐
├── .env.example           # 配置模板 ⭐
├── .gitignore            # Git忽略规则 ⭐
├── requirements.txt      # 项目依赖 ⭐
│
├── import_complete_graph.py    # 一键导入完整图谱 ⭐
├── optimize_graph.py          # 图谱优化脚本
├── optimize_article_nodes.py  # Article节点优化
├── final_verification.py      # 最终验证脚本
├── clear_graph.py            # 清空图谱脚本
│
├── README.md                   # 项目主文档
├── 知识图谱完整总结.md          # 完整总结文档
├── 图谱知识.md                 # 面试准备文档
├── 项目整理报告.md             # 文件整理报告 ⭐
├── ENV_CONFIG.md              # 环境变量配置说明 ⭐
├── ENV_MIGRATION_REPORT.md    # 环境变量迁移报告 ⭐
│
└── 待删除文件/                 # 待删除的冗余文件 ⭐
```

---

## 📊 知识图谱结构

### 整体架构

```
Document (文档)
    └── CONTAINS → StructuralUnit (章节条款)
                      ├── HAS_RULE → Rule (规则)
                      │                └── DERIVED_FROM → Article (文章) ⭐
                      ├── HAS_CONDITION → Condition (条件)
                      ├── HAS_CONSTRAINT → Constraint (约束)
                      ├── DEFINES → Definition (定义)
                      │                └── Term (术语)
                      └── REFERENCES → Reference (引用)
```

### 节点统计

| 节点类型 | 数量 | 说明 |
|---------|------|------|
| Rule | 2,945 | 规则节点（核心） |
| StructuralUnit | 1,875 | 章节条款节点 |
| Condition | 1,597 | 条件节点 |
| Constraint | 965 | 约束节点 |
| Article | 1,166 | 文章节点 ⭐ |
| Term | 193 | 术语节点 |
| Definition | 193 | 定义节点 |
| Reference | 159 | 引用节点 |
| Document | 16 | 文档节点 |

### 关系统计

| 关系类型 | 数量 | 说明 |
|---------|------|------|
| HAS_RULE | 3,138 | StructuralUnit → Rule |
| DERIVED_FROM | 2,945 | Rule → Article ⭐ |
| CONTAINS | 1,875 | Document → StructuralUnit |
| HAS_CONDITION | 1,597 | StructuralUnit → Condition |
| HAS_CONSTRAINT | 965 | StructuralUnit → Constraint |
| REFERENCES | 372 | Rule → Reference |
| DEFINES | 193 | StructuralUnit → Definition |

---

## 🚀 快速开始

### 1. 环境准备

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env

# 编辑 .env 文件，填写你的配置
# SILICONFLOW_API_KEY=your_api_key
# NEO4J_URI=neo4j+s://...
# NEO4J_USERNAME=...
# NEO4J_PASSWORD=...
# NEO4J_DATABASE=...
```

### 2. 验证配置

```bash
# 验证配置是否正确
python -m kg_extraction.config
```

**预期输出**:
```
✓ 加载配置文件: D:\Pycode\vibecoding\AeroKG\.env

============================================================
配置验证
============================================================

📋 SiliconFlow API:
  API Key: 已配置
  Base URL: https://api.siliconflow.cn/v1
  Model: deepseek-ai/DeepSeek-V3

📋 Neo4j:
  URI: neo4j+s://...
  Username: ...
  Password: 已配置
  Database: ...
```

### 3. 导入完整图谱

```bash
# 一键导入（推荐）
python import_complete_graph.py
```

**执行步骤**:
1. 清空图谱
2. 导入原始数据（7,943节点，7,927关系）
3. 执行图谱优化
4. 执行Article节点优化

**最终结果**:
- ✅ 节点: 9,109个
- ✅ 关系: 10,984条
- ✅ 全文索引: 5个
- ✅ 追溯覆盖率: 100%

### 4. 验证图谱

```bash
python final_verification.py
```

---

## 💡 核心功能

### 1. 全文检索

```cypher
// 检索包含"空域"的规则
CALL db.index.fulltext.queryNodes('rule_evidence_fulltext', '空域')
YIELD node, score
MATCH (node)-[:DERIVED_FROM]->(a:Article)
RETURN node.subject, a.article_no, a.text, score
ORDER BY score DESC
LIMIT 10
```

### 2. 规则追溯

```cypher
// 从规则追溯到原文
MATCH (r:Rule)-[:DERIVED_FROM]->(a:Article)
WHERE r.subject CONTAINS '民航局'
RETURN r.subject, r.action, a.text
```

### 3. 条款关联查询

```cypher
// 查询规则及其条件约束
MATCH (s:StructuralUnit)-[:HAS_RULE]->(r:Rule)
OPTIONAL MATCH (s)-[:HAS_CONDITION]->(c:Condition)
OPTIONAL MATCH (s)-[:HAS_CONSTRAINT]->(cs:Constraint)
RETURN s.article_no, r.subject,
       collect(DISTINCT c.text) as conditions,
       collect(DISTINCT cs.text) as constraints
```

### 4. 引用关系分析

```cypher
// 查询文内引用
MATCH (r:Rule)-[:REFERENCES]->(ref:Reference)
WHERE ref.is_intra_document = true
RETURN r.subject, ref.ref_text
```

---

## 📚 文档说明

### 核心文档

1. **README.md** - 项目主文档（本文档）
2. **知识图谱完整总结.md** - 完整的图谱结构、抽取方法、优化过程总结
3. **图谱知识.md** - 面试准备文档，包含技术细节和问答
4. **ENV_CONFIG.md** - 环境变量配置详细说明 ⭐
5. **项目整理报告.md** - 项目文件整理报告 ⭐
6. **ENV_MIGRATION_REPORT.md** - 环境变量迁移报告 ⭐

### 工具脚本

| 脚本 | 用途 |
|------|------|
| `import_complete_graph.py` | 一键导入完整图谱 ⭐ |
| `optimize_graph.py` | 执行图谱优化 |
| `optimize_article_nodes.py` | Article节点优化 |
| `final_verification.py` | 验证图谱完整性 |
| `clear_graph.py` | 清空图谱数据库 |

---

## 🔧 技术架构

### 数据处理流程

```
原始文档 (DOCX/PDF)
    ↓ 文档解析
分块数据 (chunks.json)
    ↓ LLM抽取 (DeepSeek-V3)
节点和边文件 (kg_output/)
    ↓ 质量标记
候选图库 (Neo4j Aura)
    ↓ 图谱优化
完整图谱 (9,109节点, 10,984关系)
```

### LLM配置

| 配置项 | 值 | 说明 |
|--------|-----|------|
| 模型 | deepseek-ai/DeepSeek-V3 | 统一使用DeepSeek-V3 ⭐ |
| 提供商 | SiliconFlow | API提供商 |
| Temperature | 0.05 | 低温度保证稳定性 |
| Max Tokens | 800 | 最大输出token数 |
| Timeout | 45s | API超时时间 |
| 成功率 | 99.8% | 1,561/1,564成功 |
| 平均延迟 | 856ms | API响应时间 |

### 全文索引

| 索引名称 | 节点 | 属性 |
|---------|------|------|
| rule_evidence_fulltext | Rule | evidence_text |
| rule_subject_fulltext | Rule | subject |
| rule_action_fulltext | Rule | action |
| structural_unit_fulltext | StructuralUnit | title, chapter, section |
| article_fulltext | Article | text, article_no |

---

## 📈 质量指标

| 指标 | 数值 | 说明 |
|------|------|------|
| Rule追溯覆盖率 | 100% | 所有Rule都能追溯到Article |
| Article文本覆盖率 | 100% | 所有Article都有文本 |
| LLM抽取成功率 | 99.8% | 1,561/1,564成功 |
| 平均置信度 | 0.89 | 高质量抽取 |
| 全文索引数量 | 5 | 完善的检索支持 |

---

## 🎯 应用场景

### 1. 合规性检查

查询某项业务活动相关的所有规章要求，检查是否符合相关条款。

### 2. 规章关联分析

发现不同规章之间的引用关系和关联性，分析规章体系的完整性。

### 3. 主体职责梳理

梳理某个主体的所有职责和义务，明确责任边界。

### 4. 条款追溯

从规则追溯到原始条款和文档，查看原文证据。

### 5. 智能问答

基于图谱的智能问答系统，支持自然语言查询。

---

## 🔍 查询示例

### 查看图谱统计

```cypher
// 节点统计
MATCH (n)
RETURN labels(n)[0] as label, count(*) as count
ORDER BY count DESC

// 关系统计
MATCH ()-[r]->()
RETURN type(r) as type, count(*) as count
ORDER BY count DESC
```

### 查询特定主体职责

```cypher
MATCH (r:Rule)
WHERE r.subject CONTAINS '民航局'
RETURN r.subject, r.action, r.object, r.modality
ORDER BY r.modality
```

### 查询规则及其引用

```cypher
MATCH (r:Rule)-[:REFERENCES]->(ref:Reference)
RETURN r.subject, r.action, ref.ref_text, ref.is_intra_document
```

---

## 🌐 访问图谱

### Neo4j Aura Console

1. 登录: https://console.neo4j.io/
2. 点击实例: **caac-kg**
3. 点击 **"Open with Neo4j Browser"**
4. 运行Cypher查询

### 连接信息

配置文件: `.env`

```env
# SiliconFlow API 配置
SILICONFLOW_API_KEY=your_api_key_here
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V3

# Neo4j Aura 配置
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USERNAME=your_username
NEO4J_PASSWORD=your_password
NEO4J_DATABASE=your_database_name
```

**⚠️ 安全提醒**:
- 不要将 `.env` 文件提交到版本控制系统
- 使用 `.env.example` 作为配置模板
- 定期更换API密钥

---

## 📝 更新日志

### 2026-04-09

**项目整理** ⭐:
- ✅ 整理项目文件结构
- ✅ 移动18个冗余文件到"待删除文件"文件夹
- ✅ 更新项目文档，确保信息准确
- ✅ 清理重复和临时文件

### 2026-04-07

**核心功能**:
- ✅ 完成16部民航规章的知识抽取
- ✅ 构建包含9,109个节点的知识图谱
- ✅ 实现10,984条关系的关联
- ✅ 建立质量控制机制
- ✅ 部署到Neo4j Aura云端

**图谱优化**:
- ✅ 创建Article节点层，支持规则追溯
- ✅ 修复REFERENCES关系方向
- ✅ 创建5个全文索引
- ✅ 实现100%追溯覆盖率

**配置管理** ⭐:
- ✅ 统一使用 `.env` 文件管理配置
- ✅ 所有密钥从环境变量读取
- ✅ 模型统一为 DeepSeek-V3
- ✅ 添加配置验证和文档

---

## 🤝 贡献指南

### 数据质量改进

1. 查询需要审核的节点
2. 人工审核和修正
3. 更新源数据文件
4. 重新导入图谱

### 新增规章

1. 准备规章文档
2. 运行LLM抽取
3. 生成节点和边文件
4. 导入图谱

---

## 📧 联系方式

如有问题或建议，请联系项目维护者。

---

**最后更新**: 2026-04-09  
**版本**: 2.2  
**作者**: Claude AI Assistant  
**许可**: 项目内部使用
