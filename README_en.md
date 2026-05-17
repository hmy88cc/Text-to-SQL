# Text-to-SQL Data Intelligence Analytics Platform

> A comprehensive solution for natural language to SQL query conversion based on two mainstream frameworks: LangChain and Vanna.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![LangChain](https://img.shields.io/badge/LangChain-0.3.25-green.svg)](https://www.langchain.com/)
[![Vanna](https://img.shields.io/badge/Vanna-0.7.9-orange.svg)](https://vanna.ai/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Overview

This project provides two mainstream implementations for **Text-to-SQL**:

- **LangChain Solution**: Uses LangChain SQL Agent with built-in advanced features including training memory, intelligent follow-up questions, result summarization, and data visualization
- **Vanna Solution**: Uses Vanna AI framework with training memory, intelligent follow-up questions, result summarization, and Chart.js data visualization

Both solutions are powered by **Qwen (Tongyi Qianwen)** large language model, integrated with **SQLite** lightweight database, and served via **Flask** web framework, achieving the goal of "exploring data with natural language".

---

## Features

| Feature | LangChain | Vanna |
|---------|:---------:|:-----:|
| Natural Language to SQL | ✅ | ✅ |
| Web Interface | ✅ | ✅ |
| Training Memory | ✅ | ✅ |
| Intelligent Follow-up | ✅ | ✅ |
| Result Summarization | ✅ | ✅ |
| Data Visualization | ✅ | ✅ |
| SQL Code Display | ✅ | ✅ |
| Auto Schema Awareness | ✅ | ⚠️ |
| Code Simplicity | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| SQL Accuracy | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

---

## Project Structure

```
38 text to SQL/
├── 38-从Text-to-SQL到数据智能 LangChain/
│   └── Case-SQL-LangChain/
│       ├── langchain_web.py              # LangChain main program (Flask Web)
│       ├── heros.sql                     # King of Glory hero data source
│       └── requirements.txt              # Dependencies
│
├── 38-从Text-to-SQL到数据智能Vanna/
│   └── CASE-SQL-vanna/
│       ├── vanna-mysql-full.py           # Vanna main program (Web + Advanced features)
│       └── requirements.txt              # Dependencies
│
├── README.md                             # Chinese documentation
├── README_en.md                          # English documentation
└── LangChain与Vanna对比.md               # Detailed comparison of both solutions
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- Alibaba Cloud DashScope API Key (Qwen)

### Install Dependencies

```bash
# LangChain Solution
cd "Case-SQL-LangChain"
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# Vanna Solution
cd "CASE-SQL-vanna"
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

### Configure API Key

```bash
# Windows PowerShell
$env:DASHSCOPE_API_KEY = "your-api-key-here"

# Linux / macOS
export DASHSCOPE_API_KEY="your-api-key-here"
```

### Run LangChain Solution

```bash
cd "Case-SQL-LangChain"
python langchain_web.py
```

Visit: http://localhost:5000

### Run Vanna Solution

```bash
cd "CASE-SQL-vanna"
python vanna-mysql-full.py
```

Visit: http://localhost:8080

---

## Usage Examples

After starting the web service, simply enter natural language questions in the chat box:

| Query Type | Example Question |
|------------|-----------------|
| Basic Query | Who is the hero with the highest attack? |
| Conditional Filter | Which tanks have HP over 8000? |
| Statistical Analysis | What is the average attack growth of marksman heroes? |
| Category Statistics | How many support heroes are there? |
| Time Query | Which heroes were released after 2016? |
| Range Comparison | What are the counts of ranged vs melee heroes? |

### Data Visualization

Query results automatically generate visual charts with the following features:

- **Smart Chart Recommendation**: Automatically selects appropriate chart types based on question keywords
- **Multi-Chart Switching**: Freely switch between bar charts, line charts, and pie charts
- **Interactive Exploration**: Hover to view detailed data, supports zooming and panning

---

## Architecture Comparison

### LangChain SQL Agent

```
User Question → Agent → SQLDatabaseToolkit → SQLite → Results
                   │
                   ├── LLM (Qwen3-max)
                   ├── Schema (Table Structure)
                   └── Tools (Query/Execute)
```

**Core Code** (Only 5 lines):

```python
db = SQLDatabase.from_uri(f"sqlite:///{db_path}")
llm = ChatOpenAI(model="qwen3-max-2026-01-23", ...)
agent = create_sql_agent(
    llm=llm,
    toolkit=SQLDatabaseToolkit(db=db, llm=llm),
    agent_type="tool-calling",
)
res = agent.invoke({"input": "Who has the highest attack?"})
```

### Vanna Framework

```
User Question → LLM → Prompt (Schema+Rules) → SQL → extract_sql() → SQLite → Results
                                                         │
                                                         ▼
                                                AgentMemory (Training Memory)
```

**Core Code** (Requires custom components):

```python
class MyVanna(ChromaDB_VectorStore, OpenAI_Chat): ...
vn = MyVanna(config={'model': 'qwen-turbo-latest'}, client=client)
vn.connect_to_mysql(host='...', dbname='...', user='...', password='...')
sql, df, _ = vn.ask("Who has the highest attack?")
```

---

## Detailed Comparison

| Dimension | LangChain | Vanna | Recommended Scenario |
|-----------|:---------:|:-----:|---------------------|
| Code Simplicity | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | Quick Demo → LangChain |
| Feature Completeness | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Production → Vanna |
| Learning Curve | ⭐⭐⭐⭐ | ⭐⭐⭐ | Beginners → LangChain |
| SQL Accuracy | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Complex Queries → Vanna |
| Customizability | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Deep Customization → Vanna |
| Advanced Features | Requires Extension | Built-in | Follow-up/Summary → Vanna |

### Decision Tree

```
                    Start
                      │
                      ▼
             ┌──────────────────┐
             │ Want quick setup? │
             └────────┬─────────┘
                      │
         ┌────────────┴────────────┐
         │ Yes                     │ No
         ▼                         ▼
  ┌─────────────┐          ┌──────────────────┐
  │   LangChain  │          │ Need training memory? │
  └─────────────┘          └────────┬──────────┘
                                    │
                        ┌───────────┴───────────┐
                        │ Yes                   │ No
                        ▼                       ▼
                 ┌─────────────┐        ┌──────────────────┐
                 │    Vanna    │        │ Complex queries?  │
                 └─────────────┘        └──────┬───────────┘
                                              │
                                   ┌──────────┴──────────┐
                                   │ Yes                 │ No
                                   ▼                     ▼
                            ┌─────────────┐       ┌─────────────┐
                            │    Vanna    │       │   LangChain  │
                            └─────────────┘       └─────────────┘
```

---

## Tech Stack

| Layer | Technology | Description |
|-------|------------|-------------|
| **Frontend** | HTML + CSS + JavaScript | Native implementation, no framework dependency |
| **Backend** | Flask | Lightweight Python web framework |
| **AI Framework** | LangChain / Vanna | Core Text-to-SQL frameworks |
| **Database** | SQLite | Lightweight embedded database |
| **LLM** | Qwen3-max / Qwen-Turbo | Alibaba Tongyi Qianwen model |
| **API Gateway** | DashScope | Alibaba Cloud API service |

---

## Key Optimizations

### 1. Enhanced System Prompt

```python
system_prompt = f"""You are a professional SQL generator.
Database tables: {tables_desc}

Rules [MUST STRICTLY FOLLOW]:
1. Output only one clean SELECT statement, no text, no explanation, no ```
2. When user asks "attack", always use attack_max field
3. For top-N queries, use ORDER BY ... DESC LIMIT ...
4. Do not output any extra content
5. Field and table names must be in English
"""
```

### 2. Brute-Force SQL Extraction

```python
def extract_sql(text: str) -> str:
    """Extract SELECT statement directly from LLM response"""
    for line in text.split('\n'):
        line = line.strip()
        if line.upper().startswith('SELECT'):
            return line.rstrip(';') + ';'
    return ""
```

### 3. MySQL to SQLite Auto-Conversion

Vanna solution includes built-in MySQL to SQLite auto-conversion, supporting:
- `INT` → `INTEGER`
- `FLOAT/DOUBLE` → `REAL`
- `VARCHAR(n)` → `TEXT`
- Auto-removal of MySQL-specific syntax like `ENGINE`, `CHARSET`, `COMMENT`

### 4. Chart.js Data Visualization

Both solutions integrate Chart.js data visualization:
- Automatically analyzes query result structure, extracts label and value columns
- Smart chart type recommendation (bar, line, pie)
- Runtime chart type switching
- Dark tech-style chart styling consistent with overall UI

```python
def prepare_chart_data(df: pd.DataFrame, question: str) -> dict:
    """Auto-analyze DataFrame, generate Chart.js chart data"""
    # Smart identification of label and value columns
    # Auto-recommend chart type
    # Return standardized chart data structure
```

---

## Related Documentation

- [Text-to-SQL Project Summary](./Text-to-SQL项目总结.md)

---

## License

MIT License

---

## Star History

If this project helps you, please give it a Star ⭐!
