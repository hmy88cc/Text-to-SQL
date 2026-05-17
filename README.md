# Text-to-SQL 数据智能分析平台

> 基于 LangChain 和 Vanna 两种主流框架，实现自然语言转 SQL 查询的完整解决方案。

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![LangChain](https://img.shields.io/badge/LangChain-0.3.25-green.svg)](https://www.langchain.com/)
[![Vanna](https://img.shields.io/badge/Vanna-0.7.9-orange.svg)](https://vanna.ai/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📌 项目简介

本项目提供了 **Text-to-SQL** 的两种主流实现方案：

- **LangChain 方案**：使用 LangChain SQL Agent，内置训练记忆、智能追问、结果摘要、数据可视化等高级功能
- **Vanna 方案**：使用 Vanna AI 框架，支持训练记忆、智能追问、结果摘要、Chart.js 数据可视化等高级功能

两种方案均基于 **通义千问（Qwen）** 大模型，对接 **SQLite** 轻量级数据库，以 **Flask** 提供 Web 服务，实现"用自然语言探索数据"的目标。

---

## ✨ 核心特性

| 特性 | LangChain | Vanna |
|------|:---------:|:-----:|
| 自然语言转 SQL | ✅ | ✅ |
| Web 交互界面 | ✅ | ✅ |
| 训练记忆 | ✅ | ✅ |
| 智能追问 | ✅ | ✅ |
| 结果摘要 | ✅ | ✅ |
| 数据可视化图表 | ✅ | ✅ |
| SQL 代码展示 | ✅ | ✅ |
| 自动 Schema 感知 | ✅ | ⚠️ |
| 代码简洁度 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| SQL 准确率 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

---

## 🏗️ 项目结构

```
38 text to SQL/
├── 38-从Text-to-SQL到数据智能 LangChain/
│   └── Case-SQL-LangChain/
│       ├── langchain_web.py              # LangChain 主程序（Flask Web）
│       ├── heros.sql                     # 王者荣耀英雄数据源
│       └── requirements.txt              # 依赖库
│
├── 38-从Text-to-SQL到数据智能Vanna/
│   └── CASE-SQL-vanna/
│       ├── vanna-mysql-full.py           # Vanna 主程序（Web + 高级功能）
│       └── requirements.txt              # 依赖库
│
├── README.md                             # 中文说明文档
├── README_en.md                          # 英文说明文档
└── LangChain与Vanna对比.md               # 两种方案详细对比文档
```

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- 阿里云 DashScope API Key（通义千问）

### 安装依赖

```bash
# LangChain 方案
cd "Case-SQL-LangChain"
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# Vanna 方案
cd "CASE-SQL-vanna"
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

### 配置 API Key

```bash
# Windows PowerShell
$env:DASHSCOPE_API_KEY = "your-api-key-here"

# Linux / macOS
export DASHSCOPE_API_KEY="your-api-key-here"
```

### 运行 LangChain 方案

```bash
cd "Case-SQL-LangChain"
python langchain_web.py
```

访问：http://localhost:5000

### 运行 Vanna 方案

```bash
cd "CASE-SQL-vanna"
python vanna-mysql-full.py
```

访问：http://localhost:8080

---

## 📖 使用示例

启动 Web 服务后，在聊天框中输入自然语言问题即可：

| 问题类型 | 示例问题 |
|---------|---------|
| 基础查询 | 攻击最高的英雄是谁？ |
| 条件筛选 | 生命值超过 8000 的坦克有哪些？ |
| 统计分析 | 射手英雄的平均攻击成长是多少？ |
| 分类统计 | 辅助英雄一共有多少名？ |
| 时间查询 | 2016年以后上线的英雄有哪些？ |
| 范围对比 | 远程英雄和近战英雄的数量分别是多少？ |

### 📊 数据可视化

查询结果会自动生成可视化图表，支持以下功能：

- **智能图表推荐**：根据问题关键词自动选择合适的图表类型
- **多图表切换**：可在柱状图、折线图、饼图之间自由切换
- **交互式探索**：鼠标悬停查看详细数据，支持缩放和拖拽

---

## 🏛️ 架构对比

### LangChain SQL Agent

```
用户问题 → Agent → SQLDatabaseToolkit → SQLite → 结果
                  │
                  ├── LLM (Qwen3-max)
                  ├── Schema (表结构)
                  └── Tools (查询/执行)
```

**核心代码**（仅需 5 行）：

```python
db = SQLDatabase.from_uri(f"sqlite:///{db_path}")
llm = ChatOpenAI(model="qwen3-max-2026-01-23", ...)
agent = create_sql_agent(
    llm=llm,
    toolkit=SQLDatabaseToolkit(db=db, llm=llm),
    agent_type="tool-calling",
)
res = agent.invoke({"input": "攻击最高的英雄是谁？"})
```

### Vanna Framework

```
用户问题 → LLM → Prompt (表结构+规则) → SQL → extract_sql() → SQLite → 结果
                                                        │
                                                        ▼
                                               AgentMemory (训练记忆)
```

**核心代码**（需自定义组件）：

```python
class MyVanna(ChromaDB_VectorStore, OpenAI_Chat): ...
vn = MyVanna(config={'model': 'qwen-turbo-latest'}, client=client)
vn.connect_to_mysql(host='...', dbname='...', user='...', password='...')
sql, df, _ = vn.ask("攻击最高的英雄是谁？")
```

---

## 📊 详细对比

| 维度 | LangChain | Vanna | 推荐场景 |
|------|:---------:|:-----:|---------|
| 代码简洁度 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | 快速 Demo 选 LangChain |
| 功能完整性 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 生产环境选 Vanna |
| 学习曲线 | ⭐⭐⭐⭐ | ⭐⭐⭐ | 新手选 LangChain |
| SQL 准确率 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 复杂查询选 Vanna |
| 可定制性 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 深度定制选 Vanna |
| 高级功能 | 需扩展 | 内置 | 需要追问/摘要选 Vanna |

### 决策树

```
                    开始选择
                       │
                       ▼
              ┌─────────────────┐
              │ 想要快速上线？   │
              └────────┬────────┘
                       │
          ┌────────────┴────────────┐
          │ Yes                     │ No
          ▼                         ▼
   ┌─────────────┐          ┌─────────────────┐
   │   LangChain  │          │ 需要训练记忆？   │
   └─────────────┘          └────────┬────────┘
                                     │
                         ┌───────────┴───────────┐
                         │ Yes                   │ No
                         ▼                       ▼
                  ┌─────────────┐        ┌─────────────────┐
                  │    Vanna    │        │ 查询很复杂？     │
                  └─────────────┘        └──────┬──────────┘
                                               │
                                    ┌──────────┴──────────┐
                                    │ Yes                 │ No
                                    ▼                     ▼
                             ┌─────────────┐       ┌─────────────┐
                             │    Vanna    │       │   LangChain  │
                             └─────────────┘       └─────────────┘
```

---

## 🛠️ 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **前端** | HTML + CSS + JavaScript | 原生实现，无框架依赖 |
| **后端** | Flask | 轻量级 Python Web 框架 |
| **AI 框架** | LangChain / Vanna | Text-to-SQL 核心框架 |
| **数据库** | SQLite | 轻量级嵌入式数据库 |
| **大模型** | Qwen3-max / Qwen-Turbo | 阿里通义千问模型 |
| **API 网关** | DashScope | 阿里云 API 服务 |

---

## 📝 关键优化

### 1. 强化系统提示词

```python
system_prompt = f"""你是专业SQL生成器。
数据库表：{tables_desc}

规则【必须严格遵守】：
1. 只输出一条干净的 SELECT 语句
2. 用户问"攻击力"一律用 attack_max 字段
3. 问前几名用 ORDER BY ... DESC LIMIT ...
4. 不准输出任何多余内容
5. 字段名、表名一律用英文
"""
```

### 2. 暴力 SQL 提取

```python
def extract_sql(text: str) -> str:
    """直接从 LLM 返回文本中提取 SELECT 语句"""
    for line in text.split('\n'):
        line = line.strip()
        if line.upper().startswith('SELECT'):
            return line.rstrip(';') + ';'
    return ""
```

### 3. MySQL → SQLite 自动转换

Vanna 方案内置了 MySQL 到 SQLite 的自动转换函数，支持：
- `INT` → `INTEGER`
- `FLOAT/DOUBLE` → `REAL`
- `VARCHAR(n)` → `TEXT`
- 自动移除 `ENGINE`、`CHARSET`、`COMMENT` 等 MySQL 特有语法

### 4. Chart.js 数据可视化

两种方案均集成了 Chart.js 数据可视化功能：
- 自动分析查询结果的数据结构，提取标签列和数值列
- 智能推荐图表类型（柱状图、折线图、饼图）
- 支持运行时图表类型切换
- 深色科技风图表样式，与整体 UI 风格统一

```python
def prepare_chart_data(df: pd.DataFrame, question: str) -> dict:
    """自动分析 DataFrame，生成 Chart.js 所需的图表数据"""
    # 智能识别标签列和数值列
    # 自动推荐图表类型
    # 返回标准化的图表数据结构
```

---

## 📚 相关文档

- [LangChain 方案详细文档](./38-从Text-to-SQL到数据智能%20LangChain/Case-SQL-LangChain/Text-to-SQL项目总结.md)
- [Vanna 方案详细文档](./38-从Text-to-SQL到数据智能Vanna/CASE-SQL-vanna/vanna总结.md)
- [LangChain vs Vanna 详细对比](./LangChain与Vanna对比.md)

---

## 📄 License

MIT License

---

## ⭐ Star History

如果这个项目对你有帮助，欢迎 Star ⭐ 支持一下！
