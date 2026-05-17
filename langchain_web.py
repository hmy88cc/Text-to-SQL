#!/usr/bin/env python
# coding: utf-8
"""
LangChain SQL Agent 高级版
数据库：heros.db
模型：qwen3-max-2026-01-23
高级功能：智能追问 + 结果摘要 + 自动训练 + 数据可视化图表
"""

import os
import json
import re
import sqlite3
from pathlib import Path
from typing import List, Dict, Any

from flask import Flask, request, jsonify, render_template_string
from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI


# ===================== 数据库 =====================
def get_sql_path():
    return Path(__file__).parent / "heros.sql"

def get_db_path():
    db_dir = Path(__file__).parent / "db"
    db_dir.mkdir(exist_ok=True)
    return db_dir / "heros.db"

def init_database():
    db_path = get_db_path()
    sql_path = get_sql_path()

    if not sql_path.exists():
        print("heros.sql 不存在")
        return None

    if db_path.exists():
        db_path.unlink()

    with open(sql_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    try:
        cursor.executescript(sql_content)
        conn.commit()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor.fetchall()]

        info = {}
        for t in tables:
            cursor.execute(f"PRAGMA table_info({t})")
            info[t] = [c[1] for c in cursor.fetchall()]

        print("数据库初始化成功")
        return info
    finally:
        conn.close()


# ===================== 训练记忆 =====================
class TrainingMemory:
    """自动训练记忆：保存成功的问答对"""
    
    def __init__(self, db_path: Path):
        self.memory_path = db_path.parent / "training_memory.json"
        self.training_data = self._load()
    
    def _load(self) -> List[Dict[str, Any]]:
        if self.memory_path.exists():
            with open(self.memory_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []
    
    def save(self, question: str, sql: str, result: str):
        self.training_data.append({
            "question": question,
            "sql": sql,
            "result_preview": result[:200],
            "timestamp": str(__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        })
        with open(self.memory_path, "w", encoding="utf-8") as f:
            json.dump(self.training_data, f, ensure_ascii=False, indent=2)
    
    def get_all(self) -> List[Dict[str, Any]]:
        return self.training_data
    
    def get_context(self) -> str:
        """获取最近 5 条训练数据作为 few-shot 上下文"""
        recent = self.training_data[-5:]
        if not recent:
            return ""
        context = "\n参考示例：\n"
        for item in recent:
            context += f"问题: {item['question']}\nSQL: {item['sql']}\n\n"
        return context
    
    def count(self) -> int:
        return len(self.training_data)


# ===================== 高级功能 =====================
def generate_summary(llm: ChatOpenAI, question: str, data: str) -> str:
    """生成结果摘要"""
    prompt = f"""你是一个数据分析专家。请根据以下查询结果，用简洁的中文总结关键发现。

用户问题：{question}
查询结果（前10行）：
{data[:2000]}

要求：
1. 用 2-3 句话总结核心结论
2. 指出数据中的关键趋势或异常
3. 不要提及表名或字段名，用自然语言描述
"""
    response = llm.invoke(prompt)
    return response.content


def generate_followup_questions(llm: ChatOpenAI, question: str, data: str, n: int = 3) -> List[str]:
    """生成智能追问建议"""
    prompt = f"""你是一个数据分析助手。根据用户刚才的查询和结果，生成 {n} 个有价值的后续追问。

用户问题：{question}
查询结果（前10行）：
{data[:2000]}

要求：
1. 问题要与当前分析主题相关
2. 问题要具体、可执行
3. 只返回问题列表，每行一个，不要编号
4. 用中文提问
"""
    response = llm.invoke(prompt)
    questions = [q.strip() for q in response.content.split("\n") if q.strip() and "?" in q or "？" in q or q.strip()]
    return questions[:n]


def extract_sql_from_response(text: str) -> str:
    """从 Agent 响应中提取 SQL 语句"""
    patterns = [
        r"```sql\s*(.*?)\s*```",
        r"```(.*?)```",
        r"(SELECT\s+.*?)(?:;|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            sql = match.group(1).strip()
            if not sql.endswith(";"):
                sql += ";"
            return sql
    return ""


def df_to_html_table(data_str: str) -> str:
    """将数据字符串转换为 HTML 表格"""
    try:
        import pandas as pd
        lines = data_str.strip().split("\n")
        if len(lines) < 2:
            return f"<pre>{data_str}</pre>"
        
        headers = re.split(r"\s{2,}|\t", lines[0])
        rows = []
        for line in lines[1:]:
            if line.strip():
                cells = re.split(r"\s{2,}|\t", line.strip())
                rows.append(cells)
        
        html = "<table><thead><tr>"
        for h in headers:
            html += f"<th>{h.strip()}</th>"
        html += "</tr></thead><tbody>"
        for row in rows:
            html += "<tr>"
            for cell in row:
                html += f"<td>{cell.strip()}</td>"
            html += "</tr>"
        html += "</tbody></table>"
        return html
    except:
        return f"<pre>{data_str}</pre>"


# ===================== Flask =====================
def create_app():
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False

    tables = init_database()
    if not tables:
        return app

    db_path = get_db_path()
    db = SQLDatabase.from_uri(f"sqlite:///{db_path}")
    training_memory = TrainingMemory(db_path)

    llm = ChatOpenAI(
        temperature=0.01,
        model="qwen3-max-2026-01-23",
        openai_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        openai_api_key=os.getenv("DASHSCOPE_API_KEY"),
    )

    agent = create_sql_agent(
        llm=llm,
        toolkit=SQLDatabaseToolkit(db=db, llm=llm),
        agent_type="tool-calling",
        verbose=False,
    )

    @app.route("/")
    def index():
        table_info_str = ""
        for t, cols in tables.items():
            table_info_str += f"表 {t}: {', '.join(cols)}\n"
        return render_template_string(HTML, tables_info=table_info_str)

    @app.route("/api/tables")
    def api_tables():
        return jsonify({"tables": tables})

    @app.route("/api/training_count")
    def api_training_count():
        return jsonify({"count": training_memory.count()})

    @app.route("/api/chat", methods=["POST"])
    def api_chat():
        data = request.get_json()
        question = data.get("message", "")
        
        try:
            context = training_memory.get_context()
            if context:
                full_input = f"{context}\n用户问题：{question}"
            else:
                full_input = question

            res = agent.invoke({"input": full_input})
            response_text = res["output"]
            
            sql = extract_sql_from_response(response_text)
            
            training_memory.save(question, sql, response_text)
            
            summary = ""
            followups = []
            if sql:
                try:
                    summary = generate_summary(llm, question, response_text)
                    followups = generate_followup_questions(llm, question, response_text)
                except:
                    pass
            
            return jsonify({
                "response": response_text,
                "sql": sql,
                "summary": summary,
                "followups": followups,
                "training_count": training_memory.count()
            })
        except Exception as e:
            return jsonify({"error": str(e)})

    return app


# ===================== 前端 =====================
HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>数据智能分析平台 - LangChain</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {
    --bg-dark: #0a0e1a;
    --bg-card: #12182e;
    --bg-card-light: #1a2240;
    --primary: #e6b800;
    --primary-light: #ffd700;
    --secondary: #7c5ce0;
    --accent: #00d4ff;
    --orange: #ff6b35;
    --text-bright: #ffffff;
    --text-dim: #8892b0;
    --border-glow: rgba(230, 184, 0, 0.3);
    --success: #38ef7d;
}

* { margin:0; padding:0; box-sizing:border-box; }

body {
    font-family:'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif;
    background: var(--bg-dark);
    color: var(--text-bright);
    height:100vh;
    overflow:hidden;
}

.grid-bg {
    position:fixed; top:0; left:0; width:100%; height:100%;
    background-image:
        linear-gradient(rgba(230, 184, 0, 0.04) 1px, transparent 1px),
        linear-gradient(90deg, rgba(230, 184, 0, 0.04) 1px, transparent 1px);
    background-size:50px 50px;
    pointer-events:none; z-index:1;
}

.top-bar {
    position:fixed; top:0; left:0; right:0; height:4px;
    background:linear-gradient(90deg, var(--primary), var(--orange), var(--secondary), var(--accent), var(--primary));
    background-size:200% 100%;
    animation:flow 3s linear infinite;
    z-index:1000;
}
@keyframes flow { 0%{background-position:0% 0%} 100%{background-position:200% 0%} }

.header {
    position:relative; z-index:100;
    background:linear-gradient(180deg, var(--bg-card) 0%, transparent 100%);
    padding:24px 40px 40px; text-align:center;
}

.main-title { display:inline-flex; flex-direction:column; align-items:center; gap:12px; }

.title-icon {
    width:72px; height:72px;
    background:linear-gradient(135deg, var(--primary), var(--orange));
    border-radius:20px; display:flex; align-items:center; justify-content:center;
    font-size:36px;
    box-shadow:0 0 50px rgba(230, 184, 0, 0.4), 0 16px 32px rgba(230, 184, 0, 0.2);
    animation:icon-pulse 2s ease-in-out infinite;
}
@keyframes icon-pulse {
    0%,100%{transform:scale(1); box-shadow:0 0 50px rgba(230, 184, 0, 0.4)}
    50%{transform:scale(1.06); box-shadow:0 0 70px rgba(230, 184, 0, 0.6)}
}

.title-text h1 {
    font-size:48px; font-weight:700; letter-spacing:6px;
    background:linear-gradient(135deg, var(--primary), var(--primary-light), var(--accent));
    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    filter:drop-shadow(0 0 20px rgba(230, 184, 0, 0.4));
}
.title-text .subtitle {
    font-size:14px; letter-spacing:10px; margin-top:8px;
    color:var(--text-dim);
    background:linear-gradient(90deg, var(--text-dim), var(--accent), var(--text-dim));
    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
}

.stats-bar {
    display:flex; justify-content:center; gap:24px; margin-top:16px;
}
.stat-item {
    background:var(--bg-card); padding:8px 20px; border-radius:12px;
    border:1px solid var(--border-glow);
}
.stat-item .num { font-size:20px; font-weight:700; color:var(--primary); }
.stat-item .label { font-size:11px; color:var(--text-dim); text-transform:uppercase; letter-spacing:1px; }

.main-layout {
    display:flex; height:calc(100vh - 180px);
    padding:0 24px; gap:20px; position:relative; z-index:10;
}

.sidebar {
    width:280px; display:flex; flex-direction:column; gap:16px;
}

.card {
    background:var(--bg-card); border-radius:16px; padding:20px;
    border:1px solid var(--border-glow);
}
.card-title {
    font-size:14px; font-weight:700; color:var(--primary);
    margin-bottom:14px; display:flex; align-items:center; gap:8px;
    text-transform:uppercase; letter-spacing:2px;
}
.card-title::after {
    content:''; flex:1; height:1px;
    background:linear-gradient(90deg, var(--primary), transparent);
}

.table-name {
    font-size:22px; font-weight:700; color:var(--text-bright); margin-bottom:8px;
}
.table-badge {
    display:inline-flex; align-items:center; gap:6px;
    background:linear-gradient(135deg, var(--primary), var(--orange));
    color:var(--bg-dark); padding:4px 12px; border-radius:16px;
    font-size:12px; font-weight:700;
}

.feature-item {
    display:flex; align-items:center; gap:10px; padding:10px;
    background:var(--bg-card-light); border-radius:10px; margin-bottom:8px;
    border-left:3px solid; transition:all 0.3s;
}
.feature-item:hover { transform:translateX(4px); }
.feature-item .icon { font-size:18px; }
.feature-item .text { font-size:13px; color:var(--text-dim); }

.chat-area { flex:1; display:flex; flex-direction:column; }

.chat-messages {
    flex:1; overflow-y:auto; padding:20px;
    display:flex; flex-direction:column; gap:16px;
}

.message { max-width:85%; animation:fadeIn 0.3s ease; }
@keyframes fadeIn { from{opacity:0; transform:translateY(10px)} to{opacity:1; transform:translateY(0)} }

.message.user { align-self:flex-end; }
.message.user .bubble {
    background:linear-gradient(135deg, var(--secondary), #5a3fd6);
    color:white; padding:14px 18px; border-radius:18px 4px 18px 18px;
    font-size:14px; line-height:1.6;
}

.message.assistant { align-self:flex-start; }
.message.assistant .bubble {
    background:var(--bg-card); border:1px solid var(--border-glow);
    padding:16px; border-radius:4px 18px 18px 18px;
    font-size:14px; line-height:1.8; color:var(--text-bright);
}

.sql-block {
    background:#1e293b; border-radius:8px; padding:12px; margin:10px 0;
    position:relative; font-family:'Consolas','Courier New',monospace;
    font-size:13px; color:#e2e8f0; overflow-x:auto;
}
.sql-block .sql-label {
    font-size:11px; color:var(--accent); margin-bottom:6px;
    text-transform:uppercase; letter-spacing:1px;
}
.sql-block .copy-btn {
    position:absolute; top:8px; right:8px;
    background:rgba(255,255,255,0.1); border:none; color:var(--text-dim);
    padding:4px 10px; border-radius:6px; font-size:11px; cursor:pointer;
    transition:all 0.2s;
}
.sql-block .copy-btn:hover { background:var(--primary); color:var(--bg-dark); }

.summary-block {
    background:linear-gradient(135deg, rgba(56, 239, 125, 0.1), rgba(0, 212, 255, 0.1));
    border:1px solid rgba(56, 239, 125, 0.3); border-radius:10px;
    padding:14px; margin:10px 0;
}
.summary-block .summary-label {
    font-size:11px; color:var(--success); margin-bottom:6px;
    text-transform:uppercase; letter-spacing:1px; font-weight:700;
}
.summary-block p { font-size:14px; line-height:1.7; color:var(--text-bright); }

.chart-container {
    background:var(--bg-card-light); border-radius:10px; padding:16px;
    margin:10px 0; border:1px solid var(--border-glow);
}
.chart-container .chart-label {
    font-size:11px; color:var(--accent); margin-bottom:10px;
    text-transform:uppercase; letter-spacing:1px; font-weight:700;
}
.chart-container canvas { max-height:300px; }

.followup-btns { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
.followup-btn {
    background:rgba(124, 92, 224, 0.2); border:1px solid var(--secondary);
    color:var(--secondary-light); padding:8px 14px; border-radius:20px;
    font-size:12px; cursor:pointer; transition:all 0.3s;
}
.followup-btn:hover {
    background:var(--secondary); color:white; transform:translateY(-2px);
}

.loading { display:flex; gap:6px; padding:8px 0; }
.loading span {
    width:8px; height:8px; background:var(--primary); border-radius:50%;
    animation:bounce 1.4s infinite ease-in-out;
}
.loading span:nth-child(1){animation-delay:-0.32s}
.loading span:nth-child(2){animation-delay:-0.16s}
@keyframes bounce { 0%,80%,100%{transform:scale(0)} 40%{transform:scale(1)} }

.input-area {
    padding:16px 24px; background:var(--bg-card);
    border-top:1px solid var(--border-glow);
}
.input-wrapper {
    display:flex; gap:10px; max-width:1000px; margin:0 auto;
    background:var(--bg-card-light); border:2px solid var(--border-glow);
    border-radius:14px; padding:6px; transition:all 0.2s;
}
.input-wrapper:focus-within { border-color:var(--primary); box-shadow:0 0 20px rgba(230, 184, 0, 0.2); }
.input-wrapper input {
    flex:1; background:transparent; border:none; outline:none;
    color:var(--text-bright); font-size:14px; padding:10px 14px;
}
.input-wrapper input::placeholder { color:var(--text-dim); }
.send-btn {
    width:44px; height:44px;
    background:linear-gradient(135deg, var(--primary), var(--orange));
    border:none; border-radius:10px; cursor:pointer;
    display:flex; align-items:center; justify-content:center;
    transition:all 0.2s;
}
.send-btn:hover { transform:scale(1.05); }
.send-btn svg { fill:var(--bg-dark); width:18px; height:18px; }

::-webkit-scrollbar { width:6px; }
::-webkit-scrollbar-track { background:rgba(255,255,255,0.05); }
::-webkit-scrollbar-thumb { background:rgba(230, 184, 0, 0.3); border-radius:3px; }
</style>
</head>
<body>
<div class="grid-bg"></div>
<div class="top-bar"></div>

<div class="header">
    <div class="main-title">
        <div class="title-icon">🔮</div>
        <div class="title-text">
            <h1>数据智能分析平台</h1>
            <div class="subtitle">POWERED BY LANGCHAIN AI</div>
        </div>
    </div>
    <div class="stats-bar">
        <div class="stat-item">
            <div class="num" id="trainingCount">0</div>
            <div class="label">训练样本</div>
        </div>
        <div class="stat-item">
            <div class="num" id="queryCount">0</div>
            <div class="label">查询次数</div>
        </div>
    </div>
</div>

<div class="main-layout">
    <div class="sidebar">
        <div class="card">
            <div class="card-title">📊 数据表</div>
            <div class="table-name">heros</div>
            <div class="table-badge">王者荣耀英雄数据</div>
        </div>
        <div class="card">
            <div class="card-title">✨ 高级功能</div>
            <div class="feature-item" style="border-color:var(--success)">
                <span class="icon">🧠</span>
                <span class="text">自动训练记忆</span>
            </div>
            <div class="feature-item" style="border-color:var(--accent)">
                <span class="icon">📝</span>
                <span class="text">AI 结果摘要</span>
            </div>
            <div class="feature-item" style="border-color:var(--secondary)">
                <span class="icon">💬</span>
                <span class="text">智能追问</span>
            </div>
            <div class="feature-item" style="border-color:var(--orange)">
                <span class="icon">📈</span>
                <span class="text">数据可视化</span>
            </div>
        </div>
        <div class="card">
            <div class="card-title">💡 示例问题</div>
            <div class="feature-item" style="border-color:var(--primary); cursor:pointer" onclick="ask('攻击最高的英雄是谁？')">
                <span class="icon">⚔️</span>
                <span class="text">攻击最高的英雄</span>
            </div>
            <div class="feature-item" style="border-color:var(--accent); cursor:pointer" onclick="ask('生命值最高的坦克英雄有哪些？')">
                <span class="icon">🛡️</span>
                <span class="text">最强坦克</span>
            </div>
            <div class="feature-item" style="border-color:var(--secondary); cursor:pointer" onclick="ask('射手英雄的平均攻击成长是多少？')">
                <span class="icon">🏹</span>
                <span class="text">射手属性分析</span>
            </div>
            <div class="feature-item" style="border-color:var(--orange); cursor:pointer" onclick="ask('2016年以后上线的英雄有哪些？')">
                <span class="icon">📅</span>
                <span class="text">新英雄查询</span>
            </div>
        </div>
    </div>

    <div class="chat-area">
        <div class="chat-messages" id="chatArea">
            <div class="message assistant">
                <div class="bubble">
                    欢迎使用数据智能分析平台！<br><br>
                    我可以帮你用自然语言查询数据，并提供：<br>
                    <strong>•</strong> SQL 语句展示与复制<br>
                    <strong>•</strong> AI 自动结果摘要<br>
                    <strong>•</strong> 智能追问建议<br>
                    <strong>•</strong> 数据可视化图表<br>
                    <strong>•</strong> 自动训练记忆<br><br>
                    点击左侧示例问题或直接输入你的问题吧！
                </div>
            </div>
        </div>
    </div>
</div>

<div class="input-area">
    <div class="input-wrapper">
        <input id="question" placeholder="输入你的问题..." onkeypress="if(event.key==='Enter')sendMsg()" />
        <button class="send-btn" onclick="sendMsg()">
            <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
        </button>
    </div>
</div>

<script>
let isLoading = false;
let queryCount = 0;
let chartInstances = [];

function ask(q) {
    document.getElementById('question').value = q;
    sendMsg();
}

function sendMsg() {
    if(isLoading) return;
    const q = document.getElementById('question').value.trim();
    if(!q) return;

    const chatArea = document.getElementById('chatArea');
    chatArea.innerHTML += `<div class="message user"><div class="bubble">${q}</div></div>`;
    chatArea.innerHTML += `<div class="message assistant" id="loadingMsg"><div class="bubble"><div class="loading"><span></span><span></span><span></span></div></div></div>`;
    chatArea.scrollTop = chatArea.scrollHeight;
    document.getElementById('question').value = '';
    isLoading = true;

    fetch('/api/chat', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({message:q})
    })
    .then(r=>r.json())
    .then(d=>{
        document.getElementById('loadingMsg').remove();
        
        let html = '<div class="bubble">';
        
        if(d.sql) {
            html += `<div class="sql-block">
                <div class="sql-label">📋 生成的 SQL</div>
                <button class="copy-btn" onclick="copySql(this)">复制</button>
                <code>${escapeHtml(d.sql)}</code>
            </div>`;
        }
        
        html += `<div>${formatResponse(d.response || d.error)}</div>`;
        
        if(d.summary) {
            html += `<div class="summary-block">
                <div class="summary-label">📝 AI 摘要</div>
                <p>${d.summary}</p>
            </div>`;
        }
        
        if(d.followups && d.followups.length > 0) {
            html += `<div style="margin-top:12px; font-size:12px; color:var(--text-dim);">💬 智能追问：</div>`;
            html += `<div class="followup-btns">`;
            d.followups.forEach(fq => {
                html += `<button class="followup-btn" onclick="ask('${escapeHtml(fq)}')">${escapeHtml(fq)}</button>`;
            });
            html += `</div>`;
        }
        
        html += '</div>';
        chatArea.innerHTML += `<div class="message assistant">${html}</div>`;
        
        queryCount++;
        document.getElementById('queryCount').textContent = queryCount;
        if(d.training_count !== undefined) {
            document.getElementById('trainingCount').textContent = d.training_count;
        }
        
        chatArea.scrollTop = chatArea.scrollHeight;
        isLoading = false;
    })
    .catch(e=>{
        document.getElementById('loadingMsg').remove();
        chatArea.innerHTML += `<div class="message assistant"><div class="bubble">请求失败: ${e}</div></div>`;
        isLoading = false;
    });
}

function copySql(btn) {
    const code = btn.parentElement.querySelector('code').textContent;
    navigator.clipboard.writeText(code).then(() => {
        btn.textContent = '已复制';
        setTimeout(() => btn.textContent = '复制', 1500);
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatResponse(text) {
    if(!text) return '';
    text = escapeHtml(text);
    text = text.replace(/\\n/g, '<br>');
    text = text.replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>');
    return text;
}

fetch('/api/training_count').then(r=>r.json()).then(d=>{
    document.getElementById('trainingCount').textContent = d.count;
});
</script>
</body>
</html>
"""

# ===================== main =====================
if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000)
