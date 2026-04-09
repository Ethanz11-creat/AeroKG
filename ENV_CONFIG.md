# 环境变量配置说明

## 📋 概述

本项目使用 `.env` 文件统一管理所有敏感配置信息，包括 API 密钥和数据库连接信息。

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 创建配置文件

```bash
# 复制模板文件
cp .env.example .env

# 编辑 .env 文件，填写你的实际配置
```

### 3. 配置内容

编辑 `.env` 文件，填写以下信息：

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

---

## 📝 配置项说明

### SiliconFlow API

| 配置项 | 说明 | 获取方式 |
|--------|------|---------|
| SILICONFLOW_API_KEY | API 密钥 | https://cloud.siliconflow.cn/ |
| SILICONFLOW_BASE_URL | API 地址 | 默认: https://api.siliconflow.cn/v1 |
| SILICONFLOW_MODEL | 模型名称 | 默认: deepseek-ai/DeepSeek-V3 |

### Neo4j Aura

| 配置项 | 说明 | 获取方式 |
|--------|------|---------|
| NEO4J_URI | 连接地址 | https://console.neo4j.io/ |
| NEO4J_USERNAME | 用户名 | 创建实例时设置 |
| NEO4J_PASSWORD | 密码 | 创建实例时设置 |
| NEO4J_DATABASE | 数据库名称 | 创建实例时设置 |

### 可选配置

```env
# LLM 参数配置（可选）
LLM_TEMPERATURE=0.05
LLM_MAX_TOKENS=800
LLM_TIMEOUT=45
LLM_DELAY_SECONDS=0.2
LLM_MAX_RETRIES=1
LLM_MAX_CONCURRENCY=3
```

---

## 🔒 安全说明

### ⚠️ 重要提醒

1. **不要提交 .env 文件到版本控制系统**
   - `.gitignore` 已配置忽略 `.env` 文件
   - 只提交 `.env.example` 模板文件

2. **密钥安全**
   - 定期更换 API 密钥
   - 不要在代码中硬编码密钥
   - 不要在日志中输出密钥

3. **权限管理**
   - 限制 .env 文件的访问权限
   - 不要分享包含密钥的 .env 文件

---

## 🔧 使用方法

### 在代码中使用

```python
from kg_extraction.config import get_api_key, get_neo4j_config
from kg_extraction.env_loader import load_env_config

# 加载配置
load_env_config()

# 获取 API Key
api_key = get_api_key()

# 获取 Neo4j 配置
neo4j_config = get_neo4j_config()
```

### 验证配置

```bash
# 验证配置是否正确
python -m kg_extraction.config
```

---

## 📂 文件结构

```
AeroKG/
├── .env                 # 实际配置文件（不提交）
├── .env.example         # 配置模板（提交）
├── .gitignore          # Git 忽略规则
├── requirements.txt    # 项目依赖
│
└── kg_extraction/
    ├── config.py       # 配置管理
    └── env_loader.py   # 环境变量加载器
```

---

## 🔄 迁移说明

### 从 .env.neo4j 迁移

如果你之前使用 `.env.neo4j` 文件：

1. **迁移内容**：将 `.env.neo4j` 中的配置复制到 `.env` 文件
2. **删除旧文件**：确认迁移成功后，可以删除 `.env.neo4j`
3. **更新脚本**：所有脚本已自动更新为使用 `.env` 文件

### 迁移步骤

```bash
# 1. 创建新的 .env 文件
cat .env.neo4j >> .env

# 2. 添加 SiliconFlow API 配置
echo "SILICONFLOW_API_KEY=your_key" >> .env

# 3. 验证配置
python -m kg_extraction.config

# 4. 删除旧文件（可选）
rm .env.neo4j
```

---

## ❓ 常见问题

### Q1: 配置文件找不到？

**错误**: `⚠️  未找到配置文件: .env`

**解决**:
```bash
# 确认 .env 文件在项目根目录
ls -la .env

# 如果不存在，创建它
cp .env.example .env
```

### Q2: API Key 未配置？

**错误**: `未配置 SILICONFLOW_API_KEY！`

**解决**:
```bash
# 编辑 .env 文件
nano .env

# 添加 API Key
SILICONFLOW_API_KEY=your_actual_api_key_here
```

### Q3: Neo4j 连接失败？

**错误**: `❌ 连接失败: ...`

**解决**:
1. 检查 Neo4j Aura 实例是否运行
2. 验证 URI、用户名、密码是否正确
3. 检查网络连接
4. 确认数据库是否已创建

### Q4: 如何查看当前配置？

```bash
# 查看配置信息
python -m kg_extraction.config
```

---

## 📚 相关文档

- [README.md](README.md) - 项目主文档
- [requirements.txt](requirements.txt) - 项目依赖
- [.env.example](.env.example) - 配置模板

---

## ✅ 配置检查清单

- [ ] 已安装 `python-dotenv` 包
- [ ] 已创建 `.env` 文件
- [ ] 已配置 `SILICONFLOW_API_KEY`
- [ ] 已配置 Neo4j 连接信息
- [ ] 已验证配置正确性
- [ ] 已将 `.env` 添加到 `.gitignore`

---

**最后更新**: 2026-04-07
