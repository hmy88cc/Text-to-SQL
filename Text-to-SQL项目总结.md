# Text-to-SQL 数据智能分析系统

## 一、什么是 Text-to-SQL？

**Text-to-SQL** 是将自然语言转换为 SQL 查询语句的技术，让非技术人员也能用日常语言查询数据库。

```
用户提问                    SQL 查询                  查询结果
     │                        │                        │
     ▼                        ▼                        ▼
"攻击最高的英雄是谁？"  →  SELECT name FROM heros   →  百里守约
                        ORDER BY attack_max DESC
                         LIMIT 1;
```

### 传统方式 vs Text-to-SQL

| 对比项 | 传统方式 | Text-to-SQL |
|--------|----------|-------------|
| 技术门槛 | 需要懂 SQL | 只需会说话 |
| 查询效率 | 慢，需要手写调试 | 快，AI 直接生成 |
| 复杂查询 | 容易出错 | 语义理解准确 |
| 学习成本 | 高 | 低 |

---

## 二、LangChain 核心模块

LangChain 是一个用于构建 LLM 应用的框架，主要包含以下模块：

### 2.1 核心组件

| 模块 | 作用 | 本项目中的使用 |
|------|------|---------------|
| **LLM (大语言模型)** | 理解自然语言、生成 SQL | Qwen3-max |
| **Prompt Template** | 构建提示词，引导模型生成 | SQL Agent 内置 |
| **Chain** | 连接多个组件形成流水线 | SQL Agent Chain |
| **Agent** | 自主决策执行工具 | create_sql_agent |

### 2.2 关键工具包

```python
# 数据库相关
from langchain_community.agent_toolkits import create_sql_agent    # SQL Agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit  # SQL 工具包
from langchain_community.utilities import SQLDatabase               # 数据库连接

# 模型相关
from langchain_openai import ChatOpenAI                              # 通用的 ChatGPT 兼容接口
```

### 2.3 Agent 工作流程

```
用户输入 → Agent 思考 → 选择工具 → 执行 SQL → 返回结果
    │          │           │          │          │
    ▼          ▼           ▼          ▼          ▼
自然语言   "需要查       schema      sqlite3   自然语言
          数据库"       工具                    回答
```

---

## 三、为什么选择 LangChain？

### 3.1 优势

1. **开箱即用** - 内置 SQL Agent，无需自己实现 Agent 逻辑
2. **Schema 感知** - 自动读取数据库表结构，让模型知道有哪些字段
3. **错误处理** - 自动重试、异常捕获
4. **多数据库支持** - SQLite、PostgreSQL、MySQL 等

### 3.2 对比纯 API 调用

| 方案 | LangChain SQL Agent | 纯 API 调用 |
|------|-------------------|-------------|
| 代码量 | 少（几行） | 多（需要自己实现 Agent） |
| 可靠性 | 高（有完善的重试机制） | 中（需要自己处理错误） |
| 可扩展性 | 高（工具包可自定义） | 低 |
| 学习成本 | 低 | 高 |

---

## 四、LangChain 高级功能

### 4.1 训练记忆 (TrainingMemory)

自动保存成功的问答对，形成 few-shot 上下文，提升后续查询准确率：

```python
class TrainingMemory:
    """自动训练记忆：保存成功的问答对"""
    
    def save(self, question: str, sql: str, result: str):
        # 保存到 JSON 文件
        self.training_data.append({
            "question": question,
            "sql": sql,
            "result_preview": result[:200],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    
    def get_context(self) -> str:
        """获取最近 5 条训练数据作为 few-shot 上下文"""
        recent = self.training_data[-5:]
        context = "\n参考示例：\n"
        for item in recent:
            context += f"问题: {item['question']}\nSQL: {item['sql']}\n\n"
        return context
```

### 4.2 智能追问 (Follow-up Questions)

基于当前查询结果，AI 自动生成有价值的后续问题：

```python
def generate_followup_questions(llm, question, data, n=3):
    prompt = f"""你是一个数据分析助手。根据用户刚才的查询和结果，生成 {n} 个有价值的后续追问。
用户问题：{question}
查询结果：{data[:2000]}
要求：问题要具体、可执行，与当前分析主题相关"""
    response = llm.invoke(prompt)
    return [q.strip() for q in response.content.split("\n") if q.strip()][:n]
```

### 4.3 结果摘要 (Summary)

将枯燥的数据转换为简洁的自然语言总结：

```python
def generate_summary(llm, question, data):
    prompt = f"""你是一个数据分析专家。请根据以下查询结果，用简洁的中文总结关键发现。
用户问题：{question}
查询结果：{data[:2000]}
要求：用 2-3 句话总结核心结论，指出关键趋势或异常"""
    return llm.invoke(prompt).content
```

### 4.4 数据可视化 (Chart.js)

自动分析查询结果，生成可视化图表：

- **智能图表推荐**：根据问题关键词自动选择合适的图表类型
- **多图表切换**：支持柱状图、折线图、饼图自由切换
- **交互式探索**：鼠标悬停查看详细数据

---

## 五、Vanna 核心架构

Vanna 是一个专为 Text-to-SQL 设计的 AI 框架，采用模块化架构：

### 5.1 核心组件

| 组件 | 作用 | 本项目中的实现 |
|------|------|---------------|
| **LlmService** | LLM 服务接口 | DashScopeLlmService（通义千问） |
| **SqlRunner** | SQL 执行器 | SqliteRunnerWithMemory（带训练记忆） |
| **AgentMemory** | 训练记忆存储 | DemoAgentMemory |
| **ToolRegistry** | 工具注册中心 | 注册 SQL 查询工具 |
| **UserResolver** | 用户解析器 | SimpleUserResolver |
| **Agent** | AI 智能体 | Vanna Agent |

### 5.2 自定义 LLM 服务

```python
class DashScopeLlmService(LlmService):
    """通义千问 LLM 服务"""
    
    def __init__(self, model="qwen3-max-2026-01-23", api_key=None):
        self.model = model
        self.client = OpenAI(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=api_key or os.getenv("DASHSCOPE_API_KEY"),
        )
    
    async def send_request(self, request: LlmRequest) -> LlmResponse:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": msg.role, "content": msg.content} for msg in request.messages],
            temperature=request.temperature or 0.7,
        )
        return LlmResponse(content=response.choices[0].message.content, ...)
```

### 5.3 带记忆的 SQL 执行器

```python
class SqliteRunnerWithMemory(SqlRunner):
    """SQLite 数据库运行器 + 自动训练记忆"""
    
    async def run_sql(self, args: RunSqlToolArgs, context) -> pd.DataFrame:
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()
        cursor.execute(args.sql)
        
        # 执行查询
        rows = cursor.fetchall()
        df = pd.DataFrame([dict(row) for row in rows])
        
        # 自动训练：保存问答对
        if hasattr(context, 'question') and context.question:
            self.training_data.append({
                'question': context.question,
                'sql': args.sql,
                'df': df
            })
        return df
```

### 5.4 Vanna 高级功能

- **auto_train 自动学习**：查询成功后自动写入训练样本
- **generate_followup_questions 智能追问**：基于结果推荐后续分析方向
- **generate_summary 结果摘要**：将数据转换为易懂的自然语言
- **Chart.js 数据可视化**：自动生成可视化图表

---

## 六、项目流程

```
┌─────────────────────────────────────────────────────────────────┐
│                        项目完整流程                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. 准备数据源                                                    │
│     heros.sql (MySQL 格式)                                      │
│     └── 需要转换为 SQLite 兼容格式                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. 数据库初始化                                                  │
│     ├── LangChain: 直接执行 SQL 脚本                              │
│     ├── Vanna: MySQL → SQLite 自动转换                           │
│     └── 获取表结构信息                                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. 初始化 AI 服务                                                │
│     ├── LangChain: create_sql_agent + SQLDatabaseToolkit         │
│     ├── Vanna: Agent + LlmService + SqlRunner + ToolRegistry     │
│     └── 配置 Qwen3-max 模型                                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. Flask Web 服务                                                │
│     ├── / 路由 → 渲染前端页面                                     │
│     ├── /api/chat → 接收问题，调用 AI，返回结果 + 图表数据         │
│     └── /api/tables → 返回表结构                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. 前端交互                                                      │
│     ├── 输入自然语言问题                                           │
│     ├── 发送到后端                                                 │
│     ├── 显示加载动画                                               │
│     ├── 展示 AI 回复 + SQL 代码                                    │
│     ├── 渲染数据表格 + 可视化图表                                  │
│     └── 显示摘要 + 智能追问建议                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 七、核心代码

### 7.1 数据库初始化

```python
def init_database():
    db_path = get_db_path()
    sql_path = get_sql_path()

    # 每次启动重新创建数据库
    if db_path.exists():
        db_path.unlink()

    # 读取 SQL 文件（必须是 SQLite 兼容格式）
    with open(sql_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    # 执行 SQL 脚本
    cursor.executescript(sql_content)
    conn.commit()

    # 获取表结构信息
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]

    info = {}
    for t in tables:
        cursor.execute(f"PRAGMA table_info({t})")
        info[t] = [c[1] for c in cursor.fetchall()]  # 字段名列表

    conn.close()
    return info
```

### 7.2 创建 SQL Agent (LangChain)

```python
# 连接 SQLite 数据库
db = SQLDatabase.from_uri(f"sqlite:///{db_path}")

# 配置 Qwen3-max 模型
llm = ChatOpenAI(
    temperature=0.01,                    # 低温度，精确回答
    model="qwen3-max-2026-01-23",        # 通义千问模型
    openai_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
    openai_api_key=os.getenv("DASHSCOPE_API_KEY"),
)

# 创建 SQL Agent（LangChain 核心）
agent = create_sql_agent(
    llm=llm,
    toolkit=SQLDatabaseToolkit(db=db, llm=llm),
    agent_type="tool-calling",
    verbose=False,
)
```

### 7.3 创建 Vanna Agent

```python
# 初始化 LLM 服务
llm_service = DashScopeLlmService(model="qwen3-max-2026-01-23")

# 初始化 SQL 执行器（带记忆）
sql_runner = SqliteRunnerWithMemory(database_path=str(db_path))

# 初始化 Agent Memory
agent_memory = DemoAgentMemory()

# 注册工具
tool_registry = ToolRegistry()
sql_tool = RunSqlTool(sql_runner=sql_runner)
tool_registry.register_local_tool(sql_tool, access_groups=["user", "admin"])

# 创建 Agent
agent = Agent(
    llm_service=llm_service,
    tool_registry=tool_registry,
    user_resolver=SimpleUserResolver(),
    agent_memory=agent_memory,
    config=AgentConfig(stream_responses=True)
)
```

### 7.4 API 接口

```python
@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json()
    question = data.get("message", "")
    
    # 获取训练记忆上下文
    context = training_memory.get_context()
    full_input = f"{context}\n用户问题：{question}" if context else question
    
    # 调用 Agent
    res = agent.invoke({"input": full_input})
    response_text = res["output"]
    
    # 提取 SQL
    sql = extract_sql_from_response(response_text)
    
    # 保存训练数据
    training_memory.save(question, sql, response_text)
    
    # 生成摘要和追问
    summary = generate_summary(llm, question, response_text)
    followups = generate_followup_questions(llm, question, response_text)
    
    return jsonify({
        "response": response_text,
        "sql": sql,
        "summary": summary,
        "followups": followups,
        "training_count": training_memory.count()
    })
```

---

## 八、技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **前端** | HTML + CSS + JavaScript + Chart.js | 原生实现，数据可视化 |
| **后端** | Flask | 轻量级 Python Web 框架 |
| **AI 框架** | LangChain / Vanna | Text-to-SQL 核心框架 |
| **数据库** | SQLite | 轻量级嵌入式数据库 |
| **大模型** | Qwen3-max | 阿里通义千问模型 |
| **API 网关** | DashScope | 阿里云 API 服务 |

### 依赖包

**LangChain 方案：**
```txt
langchain==0.3.25
langchain-community==0.3.25
langchain-openai==0.3.25
openai==1.77.0
pandas==2.2.3
flask==3.1.0
```

**Vanna 方案：**
```txt
vanna==0.7.9
openai==1.77.0
flask==3.1.0
pandas==2.2.3
```

---

## 九、关键：MySQL 转 SQLite 格式

### 9.1 问题背景

原始 `heros.sql` 是 MySQL 格式（Navicat 导出），包含大量 MySQL 特有语法，SQLite 无法直接执行：

```sql
-- MySQL 格式（不兼容）
CREATE TABLE heros (
  id INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  name VARCHAR(50) NOT NULL,
  hp_max FLOAT,
  PRIMARY KEY (id),
  ENGINE=InnoDB DEFAULT CHARSET=utf8
) ENGINE=InnoDB ... ;
```

### 9.2 SQLite 兼容格式

```sql
-- SQLite 格式（完全兼容）
CREATE TABLE heros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    hp_max REAL,
    hp_growth REAL,
    ...
);
```

### 9.3 转换规则

| MySQL | SQLite | 说明 |
|-------|--------|------|
| `INT` | `INTEGER` | SQLite 只有 5 种类型，推荐 INTEGER |
| `VARCHAR(50)` | `TEXT` | SQLite TEXT 无限长度 |
| `FLOAT` | `REAL` | 浮点数用 REAL |
| `AUTO_INCREMENT` | `AUTOINCREMENT` | 关键字不同 |
| `ENGINE=InnoDB` | 删除 | SQLite 没有引擎概念 |
| `CHARSET=utf8` | 删除 | SQLite 不需要字符集 |
| `COMMENT '注释'` | 删除 | SQLite 不支持注释 |
| `PRIMARY KEY (id)` | `PRIMARY KEY` | 可以写在字段后 |
| 反引号 \`name\` | `name` | SQLite 不需要反引号 |
| `ON UPDATE CURRENT_TIMESTAMP` | `CURRENT_TIMESTAMP` | 简化时间戳 |

### 9.4 INSERT 语句格式

```sql
-- 方式一：指定字段名（推荐）
INSERT INTO heros (name, hp_max, attack_max, role_main) VALUES 
('后羿', 7437, 385, '射手'),
('亚瑟', 8997, 318, '战士');

-- 方式二：所有字段按顺序
INSERT INTO heros VALUES (101, '后羿', 7437, ...);
```

### 9.5 注意事项

1. **字段数量必须匹配** - INSERT 的字段数 = VALUES 的值的数量
2. **ID 处理** - 如果有 `AUTOINCREMENT`，INSERT 时可以省略 id 列
3. **NULL 值** - SQLite 支持 NULL，但建议给默认值
4. **日期格式** - 存储为 TEXT 格式，如 `'2015-08-18'`

---

## 十、运行项目

### 10.1 安装依赖

**LangChain 方案：**
```bash
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple \
  langchain==0.3.25 langchain-community==0.3.25 langchain-openai==0.3.25 \
  openai==1.77.0 pandas==2.2.3 flask==3.1.0
```

**Vanna 方案：**
```bash
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple \
  vanna==0.7.9 openai==1.77.0 flask==3.1.0 pandas==2.2.3
```

### 10.2 配置环境变量

```bash
# Windows PowerShell
$env:DASHSCOPE_API_KEY="your-api-key"

# Windows CMD
set DASHSCOPE_API_KEY=your-api-key
```

### 10.3 启动服务

**LangChain 方案：**
```bash
cd Case-SQL-LangChain
python langchain_web.py
```
访问：http://localhost:5000

**Vanna 方案：**
```bash
cd CASE-SQL-vanna
python vanna-mysql-full.py
```
访问：http://localhost:8080

---

## 十一、可测试问题示例

| 类别 | 问题 |
|------|------|
| 基础查询 | 攻击最高的英雄是谁？ |
| 条件筛选 | 生命值超过 8000 的坦克有哪些？ |
| 统计分析 | 射手英雄的平均攻击成长是多少？ |
| 分类统计 | 辅助英雄一共有多少名？ |
| 时间查询 | 2016年以后上线的英雄有哪些？ |
| 范围对比 | 远程英雄和近战英雄的数量分别是多少？ |
| 排序查询 | 防御最低的五个英雄是谁？ |
| 组合条件 | 同时具备坦克和战士标签的英雄有哪些？ |

---

## 十二、总结

本项目展示了如何利用 **LangChain** 和 **Vanna** 两种主流框架快速构建 Text-to-SQL 应用：

### LangChain 方案特点
1. **简单** - 只需几行代码即可创建智能数据库助手
2. **开箱即用** - 内置 SQL Agent，自动处理 Schema 感知
3. **高级功能** - 训练记忆、智能追问、结果摘要、数据可视化

### Vanna 方案特点
1. **模块化架构** - 可自定义 LLM 服务、SQL 执行器、用户解析器
2. **自动学习** - 查询成功后自动写入训练样本，持续提升准确率
3. **高级功能** - 训练记忆、智能追问、结果摘要、Chart.js 数据可视化

> 核心就是：**让 AI 理解你的问题 → 生成正确的 SQL → 执行并返回结果 → 可视化展示**
