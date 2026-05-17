#!/usr/bin/env python
# coding: utf-8
"""
Vanna MySQL 完整版 - Web界面 + Advanced高级功能
整合自 vanna-mysql-web.py 和 vanna-mysql-advanced.py

功能：
1. Vanna Agent 最新架构
2. auto_train 自动学习
3. generate_followup_questions 智能追问
4. generate_summary 结果摘要
5. 美观的 Web 界面

数据表：heros.sql（王者荣耀英雄数据）
"""

import os
import re
import sys
import sqlite3
import pandas as pd
import asyncio
from pathlib import Path
from typing import Optional, List

# 修复 Windows 控制台中文乱码
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from openai import OpenAI
from flask import Flask, request, jsonify, render_template_string

# Vanna 核心组件
from vanna import Agent, AgentConfig
from vanna.core.registry import ToolRegistry
from vanna.core.llm import LlmService, LlmRequest, LlmResponse, LlmStreamChunk
from vanna.core.user import UserResolver, RequestContext, User
from vanna.capabilities.sql_runner import SqlRunner, RunSqlToolArgs
from vanna.integrations.local.agent_memory.in_memory import DemoAgentMemory
from vanna.tools import RunSqlTool


# ============================================================
# 自定义 LLM 服务（通义千问）
# ============================================================
class DashScopeLlmService(LlmService):
    """通义千问 LLM 服务"""
    
    def __init__(self, model: str = "qwen3-max-2026-01-23", api_key: str = None):
        self.model = model
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        
        if not self.api_key:
            raise ValueError("DASHSCOPE_API_KEY 环境变量未设置!")
        
        self.client = OpenAI(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=self.api_key,
        )
    
    async def send_request(self, request: LlmRequest) -> LlmResponse:
        messages = []
        for msg in request.messages:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=request.temperature or 0.7,
            max_tokens=request.max_tokens,
        )
        
        choice = response.choices[0]
        return LlmResponse(
            content=choice.message.content,
            finish_reason=choice.finish_reason,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            }
        )
    
    async def stream_request(self, request: LlmRequest):
        messages = []
        for msg in request.messages:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=request.temperature or 0.7,
            max_tokens=request.max_tokens,
            stream=True,
        )
        
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield LlmStreamChunk(
                    content=chunk.choices[0].delta.content,
                    finish_reason=chunk.choices[0].finish_reason if chunk.choices[0].finish_reason else None
                )
    
    async def validate_tools(self, tools):
        return []


# ============================================================
# 自定义 SQL Runner（SQLite + 自动训练）
# ============================================================
class SqliteRunnerWithMemory(SqlRunner):
    """SQLite 数据库运行器 + 自动训练记忆"""
    
    def __init__(self, database_path: str, agent_memory=None, llm_service=None):
        self.database_path = database_path
        self.agent_memory = agent_memory
        self.llm_service = llm_service
        self.training_data = []  # 存储训练样本
    
    async def run_sql(self, args: RunSqlToolArgs, context) -> pd.DataFrame:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        
        try:
            cursor = conn.cursor()
            cursor.execute(args.sql)
            
            query_type = args.sql.strip().upper().split()[0]
            
            if query_type == "SELECT":
                rows = cursor.fetchall()
                if not rows:
                    return pd.DataFrame()
                results_data = [dict(row) for row in rows]
                df = pd.DataFrame(results_data)
                
                # auto_train: 保存成功的问答
                if hasattr(context, 'question') and context.question:
                    self.training_data.append({
                        'question': context.question,
                        'sql': args.sql,
                        'df': df
                    })
                
                return df
            else:
                conn.commit()
                rows_affected = cursor.rowcount
                return pd.DataFrame({"影响行数": [rows_affected]})
        finally:
            conn.close()
    
    def get_training_data(self) -> List[dict]:
        """获取训练数据"""
        return self.training_data
    
    def add_training_data(self, question: str, sql: str, df: pd.DataFrame):
        """添加训练数据"""
        self.training_data.append({
            'question': question,
            'sql': sql,
            'df': df
        })


# ============================================================
# 自定义 User Resolver
# ============================================================
class SimpleUserResolver(UserResolver):
    async def resolve_user(self, request_context: RequestContext) -> User:
        email = request_context.cookies.get("vanna_email", "user@example.com")
        return User(
            id=email,
            username=email.split("@")[0],
            email=email,
            permissions=["user"],  # 确保包含 user 权限组
            metadata={}
        )


# ============================================================
# 数据库初始化
# ============================================================
def get_sql_file_path():
    """获取 heros.sql 文件路径"""
    current_dir = Path(__file__).parent.parent
    return current_dir / "SQL数据表源文件" / "heros.sql"

def convert_create_table(sql):
    """MySQL CREATE TABLE 转 SQLite"""
    lines = sql.split('\n')
    new_lines = []
    
    for line in lines:
        line = re.sub(r'\s+CHARACTER\s+SET\s+\w+', '', line, flags=re.IGNORECASE)
        line = re.sub(r'\s+COLLATE\s+\w+', '', line, flags=re.IGNORECASE)
        line = re.sub(r'\s*COMMENT\s*=.*?(?=,|$|\))', '', line, flags=re.IGNORECASE)
        line = re.sub(r'=\s*NULL\b', ' NULL', line, flags=re.IGNORECASE)
        line = re.sub(r'\s+USING\s+\w+', '', line, flags=re.IGNORECASE)
        line = re.sub(r'\bBIGINT\b', 'INTEGER', line, flags=re.IGNORECASE)
        line = re.sub(r'\bINT\b(?!\w)', 'INTEGER', line, flags=re.IGNORECASE)
        line = re.sub(r'\bFLOAT\b', 'REAL', line, flags=re.IGNORECASE)
        line = re.sub(r'\bDOUBLE\b', 'REAL', line, flags=re.IGNORECASE)
        # 处理 AUTO_INCREMENT 关键字
        line = re.sub(r'\s+AUTO_INCREMENT\b', '', line, flags=re.IGNORECASE)
        new_lines.append(line)
    
    sql = '\n'.join(new_lines)
    sql = re.sub(r'\)\s*ENGINE\s*=\s*\w+.*?;', ');', sql, flags=re.IGNORECASE | re.DOTALL)
    sql = re.sub(r'\s+AUTO_INCREMENT\s*=\s*\d+', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\s*ROW_FORMAT\s*=\s*\w+', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r',\s*$', '', sql)
    
    return sql

def parse_sql_file(content):
    """解析 SQL 文件"""
    statements = []
    
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    content = re.sub(r'--.*$', '', content, flags=re.MULTILINE)
    
    lines = content.split('\n')
    clean_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith('SET '):
            continue
        clean_lines.append(line)
    content = '\n'.join(clean_lines)
    
    create_pattern = r'CREATE\s+TABLE\s+[`"]?(\w+)[`"]?\s*\([^;]+\)\s*(?:ENGINE.*?)?;'
    for match in re.finditer(create_pattern, content, re.DOTALL | re.IGNORECASE):
        statements.append(('CREATE', match.group(0)))
    
    insert_pattern = r'INSERT\s+INTO\s+[`"]?(\w+)[`"]?\s*VALUES\s*\([^;]+\);'
    for match in re.finditer(insert_pattern, content, re.DOTALL | re.IGNORECASE):
        statements.append(('INSERT', match.group(0)))
    
    return statements

def create_database_from_sql(sql_path: Path, db_path: Path):
    """从 heros.sql 创建 SQLite 数据库"""
    print(f"\n{'='*60}")
    print("正在初始化数据库...")
    print(f"SQL文件路径: {sql_path}")
    print(f"数据库路径: {db_path}")
    print(f"{'='*60}")
    
    if db_path.exists():
        db_path.unlink()
        print("已删除旧数据库")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    tables_created = 0
    records_imported = 0
    
    try:
        with open(sql_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"[DEBUG] SQL文件大小: {len(content)} 字符")
        
        statements = parse_sql_file(content)
        print(f"[DEBUG] 解析出 {len(statements)} 条语句")
        
        for i, (stmt_type, stmt) in enumerate(statements[:5]):
            print(f"[DEBUG] 语句{i+1}: {stmt_type} -> {stmt[:80]}...")
        
        for stmt_type, stmt in statements:
            stmt = stmt.strip()
            
            if stmt_type == 'CREATE':
                try:
                    converted = convert_create_table(stmt)
                    cursor.execute(converted)
                    tables_created += 1
                except Exception as e:
                    print(f"  创建表失败: {e}")
            elif stmt_type == 'INSERT':
                try:
                    cursor.execute(stmt)
                    records_imported += 1
                except:
                    pass
        
        print(f"  + 成功")
        
    except Exception as e:
        print(f"  失败: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"\n{'='*60}")
    print(f"数据库初始化完成!")
    print(f"  - 创建表: {tables_created} 个")
    print(f"  - 导入数据: {records_imported} 条")
    print(f"{'='*60}\n")
    
    return tables_created

def get_table_info(db_path: Path) -> dict:
    """获取数据库表信息"""
    print(f"[DEBUG] get_table_info 查询数据库: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 先查看所有表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    all_tables = cursor.fetchall()
    print(f"[DEBUG] 所有表: {all_tables}")
    
    tables_info = {}
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = cursor.fetchall()
    
    for (table_name,) in tables:
        cursor.execute(f"PRAGMA table_info('{table_name}')")
        columns = cursor.fetchall()
        cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
        count = cursor.fetchone()[0]
        
        tables_info[table_name] = {
            "columns": [col[1] for col in columns],
            "row_count": count
        }
    
    conn.close()
    return tables_info


# ============================================================
# HTML 模板 - 深色科技游戏风格（标题居中大字）
# ============================================================
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚔️ 王者数据智能分析平台</title>
    <link href="https://fonts.googleapis.com/css2?family=Black+Han+Sans&family=Rajdhani:wght@500;600;700&family=Noto+Sans+SC:wght@400;500;700;900&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <style>
        :root {
            --bg-dark: #0a0e1a;
            --bg-card: #12182e;
            --bg-card-light: #1a2240;
            --primary: #e6b800;
            --primary-light: #ffd700;
            --secondary: #7c5ce0;
            --secondary-light: #a78bfa;
            --accent: #00d4ff;
            --accent-light: #67e8f9;
            --orange: #ff6b35;
            --text-bright: #ffffff;
            --text-dim: #8892b0;
            --border-glow: rgba(230, 184, 0, 0.3);
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Noto Sans SC', 'Rajdhani', sans-serif;
            background: var(--bg-dark);
            color: var(--text-bright);
            min-height: 100vh;
            overflow: hidden;
        }
        
        /* 科技感网格背景 */
        .grid-bg {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-image: 
                linear-gradient(rgba(230, 184, 0, 0.04) 1px, transparent 1px),
                linear-gradient(90deg, rgba(230, 184, 0, 0.04) 1px, transparent 1px);
            background-size: 50px 50px;
            pointer-events: none;
            z-index: 1;
        }
        
        /* 顶部流光条 */
        .top-bar {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, 
                var(--primary) 0%, 
                var(--orange) 25%, 
                var(--secondary) 50%, 
                var(--accent) 75%, 
                var(--primary) 100%);
            background-size: 200% 100%;
            animation: flow 3s linear infinite;
            z-index: 1000;
        }
        
        @keyframes flow {
            0% { background-position: 0% 0%; }
            100% { background-position: 200% 0%; }
        }
        
        /* 头部 - 居中大标题 */
        .header {
            position: relative;
            z-index: 100;
            background: linear-gradient(180deg, var(--bg-card) 0%, transparent 100%);
            padding: 30px 40px 50px;
            text-align: center;
        }
        
        .main-title {
            display: inline-flex;
            flex-direction: column;
            align-items: center;
            gap: 16px;
        }
        
        .title-icon {
            width: 90px;
            height: 90px;
            background: linear-gradient(135deg, var(--primary), var(--orange));
            border-radius: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 50px;
            box-shadow: 
                0 0 60px rgba(230, 184, 0, 0.5),
                0 20px 40px rgba(230, 184, 0, 0.3);
            animation: icon-pulse 2s ease-in-out infinite;
        }
        
        @keyframes icon-pulse {
            0%, 100% { transform: scale(1); box-shadow: 0 0 60px rgba(230, 184, 0, 0.5); }
            50% { transform: scale(1.08); box-shadow: 0 0 80px rgba(230, 184, 0, 0.7); }
        }
        
        .title-text h1 {
            font-family: 'Black Han Sans', 'Noto Sans SC', sans-serif;
            font-size: 64px;
            font-weight: 400;
            line-height: 1;
            letter-spacing: 8px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 30%, var(--accent) 70%, var(--secondary-light) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            filter: drop-shadow(0 0 30px rgba(230, 184, 0, 0.5));
            animation: title-glow 3s ease-in-out infinite;
        }
        
        @keyframes title-glow {
            0%, 100% { filter: drop-shadow(0 0 20px rgba(230, 184, 0, 0.4)); }
            50% { filter: drop-shadow(0 0 40px rgba(0, 212, 255, 0.6)); }
        }
        
        .title-text .subtitle {
            font-family: 'Rajdhani', sans-serif;
            font-size: 18px;
            letter-spacing: 12px;
            margin-top: 10px;
            font-weight: 600;
            background: linear-gradient(90deg, var(--text-dim), var(--accent), var(--text-dim));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        /* 统计面板 */
        .stats-panel {
            position: absolute;
            right: 40px;
            top: 50%;
            transform: translateY(-50%);
            display: flex;
            gap: 16px;
        }
        
        .stat-box {
            text-align: center;
            padding: 16px 24px;
            background: var(--bg-card);
            border-radius: 16px;
            border: 2px solid var(--border-glow);
            min-width: 100px;
        }
        
        .stat-box:hover {
            border-color: var(--primary);
            box-shadow: 0 0 20px rgba(230, 184, 0, 0.3);
        }
        
        .stat-number {
            font-family: 'Rajdhani', sans-serif;
            font-size: 36px;
            font-weight: 700;
            color: var(--primary);
        }
        
        .stat-label {
            font-size: 12px;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: 2px;
            margin-top: 4px;
        }
        
        /* 主体布局 */
        .main-layout { 
            display: flex; 
            height: calc(100vh - 180px); 
            position: relative;
            z-index: 10;
            padding: 0 30px;
            gap: 24px;
            box-sizing: border-box;
        }
        
        /* 侧边栏 */
        .sidebar {
            width: 300px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        
        /* 卡片样式 */
        .card {
            background: var(--bg-card);
            border-radius: 20px;
            padding: 24px;
            border: 1px solid var(--border-glow);
            transition: all 0.3s ease;
        }
        
        .card:hover {
            border-color: var(--primary);
            box-shadow: 0 0 30px rgba(230, 184, 0, 0.2);
        }
        
        .card-title {
            font-size: 16px;
            font-weight: 700;
            color: var(--primary);
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 10px;
            text-transform: uppercase;
            letter-spacing: 2px;
        }
        
        .card-title::after {
            content: '';
            flex: 1;
            height: 1px;
            background: linear-gradient(90deg, var(--primary), transparent);
        }
        
        /* 数据表卡片 */
        .table-name {
            font-family: 'Rajdhani', sans-serif;
            font-size: 26px;
            font-weight: 700;
            color: var(--text-bright);
            margin-bottom: 10px;
        }
        
        .table-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: linear-gradient(135deg, var(--primary), var(--orange));
            color: var(--bg-dark);
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: 700;
        }
        
        .table-info {
            margin-top: 12px;
            font-size: 14px;
            color: var(--text-dim);
        }
        
        /* 功能卡片 */
        .feature-item {
            display: flex;
            align-items: flex-start;
            gap: 14px;
            padding: 14px;
            background: var(--bg-card-light);
            border-radius: 14px;
            margin-bottom: 12px;
            border-left: 4px solid;
            transition: all 0.3s ease;
        }
        
        .feature-item:last-child { margin-bottom: 0; }
        
        .feature-item:hover {
            transform: translateX(5px);
            background: var(--bg-card);
        }
        
        .feature-item.ai { border-color: var(--primary); }
        .feature-item.learn { border-color: var(--secondary); }
        .feature-item.chat { border-color: var(--accent); }
        .feature-item.summary { border-color: var(--orange); }
        
        .feature-emoji {
            font-size: 26px;
        }
        
        .feature-text h4 {
            font-size: 16px;
            font-weight: 700;
            color: var(--text-bright);
            margin-bottom: 4px;
        }
        
        .feature-text p {
            font-size: 13px;
            color: var(--text-dim);
        }
        
        /* 聊天区域 */
        .chat-area {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: var(--bg-card);
            border-radius: 24px;
            border: 1px solid var(--border-glow);
            overflow: hidden;
            min-height: 0;
        }
        
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 30px;
            display: flex;
            flex-direction: column;
            gap: 20px;
            background: linear-gradient(180deg, var(--bg-card-light) 0%, var(--bg-card) 100%);
            min-height: 0;
        }
        
        .chat-messages::-webkit-scrollbar { width: 8px; }
        .chat-messages::-webkit-scrollbar-track { background: var(--bg-card-light); border-radius: 4px; }
        .chat-messages::-webkit-scrollbar-thumb { background: linear-gradient(var(--primary), var(--secondary)); border-radius: 4px; }
        
        /* 消息气泡 */
        .message { max-width: 78%; }
        .message.user { align-self: flex-end; }
        .message.assistant { align-self: flex-start; }
        
        .message-content {
            padding: 18px 24px;
            border-radius: 20px;
            font-size: 17px;
            line-height: 1.8;
        }
        
        .message.user .message-content {
            background: linear-gradient(135deg, var(--primary), var(--orange));
            color: var(--bg-dark);
            font-weight: 700;
            border-bottom-right-radius: 6px;
            box-shadow: 0 6px 25px rgba(230, 184, 0, 0.4);
        }
        
        .message.assistant .message-content {
            background: var(--bg-card);
            border: 1px solid var(--border-glow);
            border-bottom-left-radius: 6px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        }
        
        /* SQL 代码块 */
        .sql-block {
            background: linear-gradient(135deg, #0d1117, #161b22);
            border: 2px solid var(--accent);
            border-radius: 14px;
            padding: 18px 22px;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 15px;
            margin: 14px 0;
            overflow-x: auto;
            white-space: pre-wrap;
            word-break: break-all;
            color: var(--accent-light);
            box-shadow: 0 0 20px rgba(0, 212, 255, 0.2);
        }
        
        /* 数据表格 */
        .message-content table {
            border-collapse: collapse;
            margin: 14px 0;
            width: 100%;
            font-size: 15px;
            border-radius: 12px;
            overflow: hidden;
        }
        
        .message-content th, .message-content td {
            border: 1px solid var(--border-glow);
            padding: 12px 16px;
            text-align: left;
        }
        
        .message-content th {
            background: linear-gradient(135deg, var(--primary), var(--orange));
            color: var(--bg-dark);
            font-weight: 700;
            font-size: 15px;
        }
        
        .message-content tr:nth-child(even) { background: var(--bg-card-light); }
        .message-content tr:hover { background: rgba(230, 184, 0, 0.1); }
        
        /* 摘要框 */
        .summary-box {
            background: linear-gradient(135deg, rgba(0, 212, 255, 0.1), rgba(124, 92, 224, 0.1));
            border: 2px solid var(--accent);
            border-radius: 16px;
            padding: 18px;
            margin: 14px 0;
            font-size: 16px;
            line-height: 1.8;
        }
        
        /* 图表容器 */
        .chart-container {
            background: linear-gradient(135deg, rgba(18, 24, 46, 0.9), rgba(26, 34, 64, 0.9));
            border: 2px solid var(--primary);
            border-radius: 16px;
            padding: 20px;
            margin: 16px 0;
            box-shadow: 0 0 30px rgba(230, 184, 0, 0.2);
            position: relative;
            min-height: 300px;
        }
        
        .chart-title {
            font-size: 16px;
            font-weight: 700;
            color: var(--primary);
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .chart-wrapper {
            position: relative;
            width: 100%;
            max-height: 400px;
        }
        
        .chart-toggle {
            display: inline-flex;
            gap: 8px;
            margin-bottom: 12px;
        }
        
        .chart-toggle-btn {
            background: var(--bg-card-light);
            border: 2px solid var(--border-glow);
            border-radius: 20px;
            padding: 6px 14px;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.3s ease;
            color: var(--text-dim);
        }
        
        .chart-toggle-btn.active {
            background: linear-gradient(135deg, var(--primary), var(--orange));
            color: var(--bg-dark);
            border-color: var(--primary);
            font-weight: 700;
        }
        
        .chart-toggle-btn:hover {
            border-color: var(--primary);
            transform: scale(1.05);
        }
        
        /* 追问区域 */
        .followup-section {
            margin-top: 18px;
            padding-top: 18px;
            border-top: 2px dashed var(--border-glow);
        }
        
        .followup-title {
            font-size: 15px;
            font-weight: 700;
            color: var(--secondary-light);
            margin-bottom: 12px;
        }
        
        .followup-btn {
            display: inline-block;
            background: var(--bg-card-light);
            border: 2px solid var(--secondary);
            border-radius: 25px;
            padding: 10px 18px;
            font-size: 14px;
            margin: 6px 6px 6px 0;
            cursor: pointer;
            transition: all 0.3s ease;
            color: var(--text-bright);
            font-weight: 500;
        }
        
        .followup-btn:hover {
            background: linear-gradient(135deg, var(--secondary), var(--accent));
            color: var(--bg-dark);
            transform: scale(1.05);
            box-shadow: 0 4px 20px rgba(124, 92, 224, 0.4);
        }
        
        /* 输入区域 - 固定在底部 */
        .input-area {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            padding: 20px 40px;
            background: linear-gradient(180deg, transparent, var(--bg-dark) 30%);
            z-index: 100;
        }
        
        .input-wrapper { 
            display: flex; 
            gap: 14px; 
            align-items: center; 
            max-width: 1200px;
            margin: 0 auto;
        }
        
        .chat-input {
            flex: 1;
            padding: 20px 28px;
            background: var(--bg-card);
            border: 3px solid var(--primary);
            border-radius: 35px;
            font-size: 18px;
            color: var(--text-bright);
            transition: all 0.3s ease;
            font-family: inherit;
            box-shadow: 0 0 30px rgba(230, 184, 0, 0.3), inset 0 0 20px rgba(0,0,0,0.3);
        }
        
        .chat-input::placeholder { color: var(--text-dim); }
        
        .chat-input:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 30px rgba(230, 184, 0, 0.3);
        }
        
        .send-btn {
            padding: 18px 36px;
            background: linear-gradient(135deg, var(--primary), var(--orange));
            color: var(--bg-dark);
            border: none;
            border-radius: 30px;
            font-size: 17px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.3s ease;
            font-family: 'Noto Sans SC', sans-serif;
            box-shadow: 0 6px 25px rgba(230, 184, 0, 0.4);
            letter-spacing: 2px;
        }
        
        .send-btn:hover { 
            transform: scale(1.05);
            box-shadow: 0 8px 35px rgba(230, 184, 0, 0.6);
        }
        
        .send-btn:disabled { 
            opacity: 0.6; 
            cursor: not-allowed;
            transform: none;
        }
        
        /* 欢迎消息 */
        .welcome-msg {
            text-align: center;
            padding: 60px 40px;
            flex: 1;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }
        
        .welcome-msg h2 {
            font-family: 'Black Han Sans', 'Noto Sans SC', sans-serif;
            font-size: 48px;
            letter-spacing: 6px;
            background: linear-gradient(135deg, var(--primary), var(--primary-light), var(--accent), var(--secondary-light));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 16px;
            animation: welcome-glow 3s ease-in-out infinite;
        }
        
        @keyframes welcome-glow {
            0%, 100% { filter: drop-shadow(0 0 15px rgba(230, 184, 0, 0.5)); }
            50% { filter: drop-shadow(0 0 30px rgba(0, 212, 255, 0.8)); }
        }
        
        .welcome-msg p {
            font-size: 18px;
            color: var(--text-dim);
            margin-bottom: 30px;
        }
        
        .welcome-examples {
            display: flex;
            flex-wrap: wrap;
            gap: 14px;
            justify-content: center;
            margin-top: 10px;
        }
        
        .example-btn {
            background: var(--bg-card-light);
            border: 2px solid var(--primary);
            border-radius: 30px;
            padding: 14px 26px;
            font-size: 16px;
            cursor: pointer;
            transition: all 0.3s ease;
            color: var(--text-bright);
            font-weight: 600;
        }
        
        .example-btn:hover {
            background: linear-gradient(135deg, var(--primary), var(--orange));
            color: var(--bg-dark);
            transform: scale(1.08);
            box-shadow: 0 8px 30px rgba(230, 184, 0, 0.4);
        }
        
        /* 加载动画 */
        .typing {
            padding: 16px 30px;
            color: var(--accent);
            font-size: 16px;
            display: none;
            align-items: center;
            gap: 12px;
        }
        
        .typing.active { display: flex; }
        
        .typing-dots {
            display: flex;
            gap: 6px;
        }
        
        .typing-dots span {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            animation: dot-bounce 1.4s ease-in-out infinite;
        }
        
        .typing-dots span:nth-child(1) { background: var(--primary); }
        .typing-dots span:nth-child(2) { background: var(--orange); animation-delay: 0.15s; }
        .typing-dots span:nth-child(3) { background: var(--secondary); animation-delay: 0.3s; }
        
        @keyframes dot-bounce {
            0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
            40% { transform: scale(1.2); opacity: 1; }
        }
    </style>
</head>
<body>
    <div class="top-bar"></div>
    <div class="grid-bg"></div>
    
    <div class="header">
        <div class="main-title">
            <div class="title-icon">⚔️</div>
            <div class="title-text">
                <h1>王者数据智能分析平台</h1>
                <div class="subtitle">KING OF GLORY DATA ANALYTICS</div>
            </div>
        </div>
        <div class="stats-panel">
            <div class="stat-box">
                <div class="stat-number" id="trainCount">0</div>
                <div class="stat-label">训练样本</div>
            </div>
            <div class="stat-box">
                <div class="stat-number">68</div>
                <div class="stat-label">英雄数量</div>
            </div>
        </div>
    </div>
    
    <div class="main-layout">
        <div class="sidebar">
            <div class="card">
                <div class="card-title">📊 数据表</div>
                <div id="tableList">
                    <div class="table-name">👑 heros</div>
                    <span class="table-badge">68 条数据</span>
                    <div class="table-info">多个分析字段</div>
                </div>
            </div>
            
            <div class="card">
                <div class="card-title">⚡ 核心能力</div>
                <div class="feature-item ai">
                    <div class="feature-emoji">🧠</div>
                    <div class="feature-text">
                        <h4>智能 SQL 生成</h4>
                        <p>AI 理解自然语言，自动生成精准查询</p>
                    </div>
                </div>
                <div class="feature-item learn">
                    <div class="feature-emoji">📚</div>
                    <div class="feature-text">
                        <h4>自动学习进化</h4>
                        <p>查询成功后自动写入训练样本</p>
                    </div>
                </div>
                <div class="feature-item chat">
                    <div class="feature-emoji">💬</div>
                    <div class="feature-text">
                        <h4>智能追问建议</h4>
                        <p>基于当前结果推荐后续分析方向</p>
                    </div>
                </div>
                <div class="feature-item summary">
                    <div class="feature-emoji">📝</div>
                    <div class="feature-text">
                        <h4>结果摘要翻译</h4>
                        <p>将枯燥数据转换为易懂语言</p>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="chat-area">
            <div class="chat-messages" id="chatMessages">
                <div class="welcome-msg">
                    <h2>⚔️ 欢迎使用数据智能分析 ⚔️</h2>
                    <p>基于王者荣耀英雄数据，开启你的数据分析之旅</p>
                    <div class="welcome-examples">
                        <button class="example-btn" onclick="sendExample('查询攻击力前5名的英雄')">🏆 攻击力前5名</button>
                        <button class="example-btn" onclick="sendExample('坦克英雄有哪些')">🛡️ 坦克英雄</button>
                        <button class="example-btn" onclick="sendExample('哪些英雄生存能力最强')">💪 生存能力</button>
                        <button class="example-btn" onclick="sendExample('法师职业的平均属性')">🔮 法师属性</button>
                    </div>
                </div>
            </div>
            <div class="typing" id="typingIndicator">
                <div class="typing-dots"><span></span><span></span><span></span></div>
                <span>AI 正在分析中...</span>
            </div>
        </div>
        
        <div class="input-area">
            <div class="input-wrapper">
                <input type="text" class="chat-input" id="chatInput"
                       placeholder="输入您的问题，例如：刺客英雄的物理攻击如何？"
                       onkeypress="if(event.key==='Enter')sendMessage()">
                <button class="send-btn" id="sendBtn" onclick="sendMessage()">⚔️ 发起查询</button>
            </div>
        </div>
    </div>
    
    <script>
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        async function loadTableInfo() {
            try {
                const response = await fetch('/api/tables');
                const data = await response.json();
                const tableList = document.getElementById('tableList');
                tableList.innerHTML = '';
                
                for (const [name, info] of Object.entries(data)) {
                    const div = document.createElement('div');
                    div.innerHTML = '<div class="table-name">👑 ' + name + '</div>' +
                        '<span class="table-badge">' + info.row_count + ' 条数据</span>' +
                        '<div class="table-info">' + info.columns.length + ' 个分析字段</div>';
                    tableList.appendChild(div);
                }
            } catch (e) { console.error('加载失败:', e); }
        }
        
        async function loadTrainingCount() {
            try {
                const response = await fetch('/api/training_count');
                const data = await response.json();
                document.getElementById('trainCount').textContent = data.count;
            } catch (e) {}
        }
        
        function sendExample(question) {
            document.getElementById('chatInput').value = question;
            sendMessage();
        }
        
        async function sendMessage() {
            const input = document.getElementById('chatInput');
            const message = input.value.trim();
            if (!message) return;
            
            const chatMessages = document.getElementById('chatMessages');
            const typingIndicator = document.getElementById('typingIndicator');
            const sendBtn = document.getElementById('sendBtn');
            
            const welcome = chatMessages.querySelector('.welcome-msg');
            if (welcome) welcome.remove();
            
            chatMessages.innerHTML += '<div class="message user"><div class="message-content">' + escapeHtml(message) + '</div></div>';
            input.value = '';
            sendBtn.disabled = true;
            typingIndicator.classList.add('active');
            chatMessages.scrollTop = chatMessages.scrollHeight;
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: message})
                });
                const data = await response.json();
                typingIndicator.classList.remove('active');
                
                if (data.error) {
                    chatMessages.innerHTML += '<div class="message assistant"><div class="message-content" style="color:#ff6b6b;">❌ 错误: ' + escapeHtml(data.error) + '</div></div>';
                } else {
                    const msgId = 'msg-' + Date.now();
                    chatMessages.innerHTML += '<div class="message assistant" id="' + msgId + '"><div class="message-content">' + data.response + '</div></div>';
                    
                    // 渲染图表
                    if (data.chart_data) {
                        renderChart(msgId, data.chart_data);
                    }
                    
                    loadTrainingCount();
                }
                
            } catch (e) {
                typingIndicator.classList.remove('active');
                chatMessages.innerHTML += '<div class="message assistant"><div class="message-content" style="color:#ff6b6b;">❌ 网络错误，请重试</div></div>';
            }
            
            sendBtn.disabled = false;
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
        
        function renderChart(msgId, chartData) {
            const msgEl = document.getElementById(msgId);
            if (!msgEl || !chartData) return;
            
            const contentEl = msgEl.querySelector('.message-content');
            if (!contentEl) return;
            
            // 创建图表容器
            const chartContainer = document.createElement('div');
            chartContainer.className = 'chart-container';
            
            const chartId = 'chart-' + Date.now();
            
            chartContainer.innerHTML = `
                <div class="chart-title">📊 数据可视化</div>
                <div class="chart-toggle">
                    <button class="chart-toggle-btn active" onclick="switchChart('${chartId}', 'bar', this)">柱状图</button>
                    <button class="chart-toggle-btn" onclick="switchChart('${chartId}', 'line', this)">折线图</button>
                    ${chartData.datasets.length === 1 ? '<button class="chart-toggle-btn" onclick="switchChart(\'' + chartId + '\', \'pie\', this)">饼图</button>' : ''}
                </div>
                <div class="chart-wrapper">
                    <canvas id="${chartId}"></canvas>
                </div>
            `;
            
            contentEl.appendChild(chartContainer);
            
            // 创建图表
            const ctx = document.getElementById(chartId).getContext('2d');
            
            Chart.defaults.color = '#8892b0';
            Chart.defaults.borderColor = 'rgba(136, 146, 176, 0.1)';
            
            const chart = new Chart(ctx, {
                type: chartData.type,
                data: {
                    labels: chartData.labels,
                    datasets: chartData.datasets.map(ds => ({
                        ...ds,
                        tension: 0.4,
                        fill: chartData.type === 'line' ? {
                            target: 'origin',
                            above: 'rgba(230, 184, 0, 0.1)'
                        } : undefined
                    }))
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            labels: {
                                color: '#8892b0',
                                font: { size: 13 }
                            }
                        },
                        tooltip: {
                            backgroundColor: 'rgba(18, 24, 46, 0.95)',
                            titleColor: '#e6b800',
                            bodyColor: '#ffffff',
                            borderColor: 'rgba(230, 184, 0, 0.3)',
                            borderWidth: 1,
                            cornerRadius: 8,
                            padding: 12
                        }
                    },
                    scales: chartData.type === 'pie' ? {} : {
                        y: {
                            beginAtZero: true,
                            grid: {
                                color: 'rgba(136, 146, 176, 0.1)'
                            }
                        },
                        x: {
                            grid: {
                                color: 'rgba(136, 146, 176, 0.1)'
                            }
                        }
                    }
                }
            });
            
            // 存储图表实例
            window[chartId] = chart;
        }
        
        function switchChart(chartId, type, btn) {
            const chart = window[chartId];
            if (!chart) return;
            
            // 更新按钮状态
            const toggleBtns = btn.parentElement.querySelectorAll('.chart-toggle-btn');
            toggleBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            // 切换图表类型
            chart.config.type = type;
            
            if (type === 'line') {
                chart.data.datasets.forEach(ds => {
                    ds.fill = {
                        target: 'origin',
                        above: 'rgba(230, 184, 0, 0.1)'
                    };
                    ds.tension = 0.4;
                });
                chart.options.scales = {
                    y: {
                        beginAtZero: true,
                        grid: { color: 'rgba(136, 146, 176, 0.1)' }
                    },
                    x: {
                        grid: { color: 'rgba(136, 146, 176, 0.1)' }
                    }
                };
            } else if (type === 'pie') {
                chart.options.scales = {};
            } else {
                chart.data.datasets.forEach(ds => {
                    delete ds.fill;
                    delete ds.tension;
                });
                chart.options.scales = {
                    y: {
                        beginAtZero: true,
                        grid: { color: 'rgba(136, 146, 176, 0.1)' }
                    },
                    x: {
                        grid: { color: 'rgba(136, 146, 176, 0.1)' }
                    }
                };
            }
            
            chart.update();
        }
        
        window.onload = function() {
            loadTableInfo();
            loadTrainingCount();
        };
    </script>
</body>
</html>
'''


# ============================================================
# Flask 应用
# ============================================================
def create_app():
    app = Flask(__name__)
    
    sql_path = get_sql_file_path()
    db_path = Path(__file__).parent / "heros.db"
    
    # 初始化数据库（强制重建）
    if db_path.exists():
        db_path.unlink()
        print("[DEBUG] 已删除旧数据库")
    create_database_from_sql(sql_path, db_path)
    
    tables_info = get_table_info(db_path)
    print(f"[DEBUG] 数据库路径: {db_path}")
    print(f"[DEBUG] 表信息: {tables_info}")
    
    print("\n" + "="*60)
    print("初始化 Vanna AI 服务...")
    print("="*60)
    
    # 初始化 LLM
    try:
        llm_service = DashScopeLlmService(model="qwen3-max-2026-01-23")
        print("✓ LLM 服务初始化成功!")
    except ValueError as e:
        print(f"✗ LLM 服务初始化失败: {e}")
        print("请设置 DASHSCOPE_API_KEY 环境变量")
        llm_service = None
    
    # 初始化 SQL Runner（带记忆功能）
    sql_runner = SqliteRunnerWithMemory(database_path=str(db_path))
    
    # 初始化 Agent Memory
    agent_memory = DemoAgentMemory()
    
    # 注册工具
    tool_registry = ToolRegistry()
    sql_tool = RunSqlTool(sql_runner=sql_runner)
    tool_registry.register_local_tool(sql_tool, access_groups=["user", "admin"])
    
    # 用户解析
    user_resolver = SimpleUserResolver()
    
    # 创建 Agent
    agent = None
    if llm_service:
        agent = Agent(
            llm_service=llm_service,
            tool_registry=tool_registry,
            user_resolver=user_resolver,
            agent_memory=agent_memory,
            config=AgentConfig(stream_responses=True)
        )
        print("✓ Agent 初始化成功!")
    
    print("="*60 + "\n")
    
    app.config['AGENT'] = agent
    app.config['SQL_RUNNER'] = sql_runner
    app.config['LLM_SERVICE'] = llm_service
    app.config['TOOL_REGISTRY'] = tool_registry
    app.config['DB_PATH'] = str(db_path)
    app.config['TABLES_INFO'] = tables_info
    
    @app.route('/')
    def index():
        return render_template_string(HTML_TEMPLATE)
    
    @app.route('/api/tables')
    def get_tables():
        return jsonify(tables_info)
    
    @app.route('/api/training_count')
    def get_training_count():
        sql_runner = app.config['SQL_RUNNER']
        return jsonify({'count': len(sql_runner.get_training_data())})
    
    @app.route('/api/chat', methods=['POST'])
    def chat():
        agent = app.config['AGENT']
        sql_runner = app.config['SQL_RUNNER']
        llm_service = app.config['LLM_SERVICE']
        tool_registry = app.config['TOOL_REGISTRY']
        tables_info = app.config['TABLES_INFO']
        
        data = request.get_json()
        message = data.get('message', '')
        
        if not agent or not llm_service:
            return jsonify({'error': 'AI 服务未初始化，请设置 DASHSCOPE_API_KEY'})
        
        try:
            # 构建系统提示（包含表结构）
            tables_desc = "\n".join([
                f"- {name}: {', '.join(info['columns'])}"
                for name, info in tables_info.items()
            ])
            
            system_prompt = f"""你是专业SQL生成器。
数据库表：
{tables_desc}

规则【必须严格遵守】：
1. 只输出一条干净的 SELECT 语句，不要文字、不要解释、不要```、不要 markdown
2. 用户问"攻击力"一律用 attack_max 字段
3. 问前几名用 ORDER BY ... DESC LIMIT ...
4. 不准输出任何多余内容
5. 字段名、表名一律用英文
"""
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                async def get_response():
                    from vanna.core.user.models import User as VannaUser
                    from vanna.core.tool import ToolContext
                    
                    user_obj = VannaUser(id="user@example.com", username="user", permissions=["user"])
                    
                    # 获取 agent_memory
                    agent_memory = app.config['AGENT'].agent_memory
                    
                    # 1. LLM 生成 SQL
                    req = LlmRequest(
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": message}
                        ],
                        user=user_obj
                    )
                    
                    response = await llm_service.send_request(req)
                    print(f"[DEBUG] LLM 返回: {response.content[:500] if response.content else 'None'}")
                    sql = extract_sql(response.content)
                    print(f"[DEBUG] 提取的 SQL: {sql}")
                    
                    result_parts = []
                    
                    if sql:
                        # 2. 直接执行 SQL（绕过权限问题）
                        print(f"[DEBUG] 执行 SQL: {sql}")
                        
                        from vanna.capabilities.sql_runner import RunSqlToolArgs
                        class SimpleContext:
                            pass
                        ctx = SimpleContext()
                        ctx.question = message
                        
                        df = await sql_runner.run_sql(RunSqlToolArgs(sql=sql), ctx)
                        print(f"[DEBUG] 查询结果: {len(df)} 行")
                        
                        # 保存到训练数据
                        sql_runner.add_training_data(message, sql, df)
                        
                        # 4. 显示结果
                        result_parts.append('<div style="margin-bottom:12px;"><strong>📊 生成的 SQL:</strong></div>')
                        result_parts.append('<div class="sql-block">' + escape_html(sql) + '</div>')
                        
                        try:
                            if df is not None and not df.empty and len(df) > 0:
                                result_parts.append('<div style="margin:12px 0;"><strong>📋 查询结果:</strong></div>')
                                result_parts.append(df.to_html(index=False, escape=False))
                                
                                # 生成图表数据
                                chart_data = prepare_chart_data(df, message)
                                
                                # 5. 生成摘要
                                summary = generate_summary(message, df, llm_service)
                                if summary:
                                    result_parts.append('<div class="summary-box"><strong>📝 分析摘要:</strong><br>' + escape_html(summary) + '</div>')
                                
                                # 6. 生成追问
                                followups = generate_followup_questions(message, sql, df, llm_service)
                                if followups:
                                    followup_btns = ''.join([
                                        '<button class="followup-btn" onclick="sendExample(\'' + escape_html(q) + '\')">' + escape_html(q) + '</button>'
                                        for q in followups if q.strip()
                                    ])
                                    if followup_btns:
                                        result_parts.append('<div class="followup-section"><div class="followup-title">💬 你可能还想问:</div>' + followup_btns + '</div>')
                                
                                # 返回图表数据
                                return jsonify({
                                    'response': ''.join(result_parts),
                                    'chart_data': chart_data
                                })
                            else:
                                result_parts.append('<div style="color:#64748b;">查询结果为空</div>')
                        except Exception as e:
                            result_parts.append('<div style="color:#64748b;">处理结果出错: ' + escape_html(str(e)) + '</div>')
                    else:
                        # 非 SQL 问题，直接回答
                        result_parts.append('<div>' + escape_html(response.content) + '</div>')
                    
                    return ''.join(result_parts)
                
                result = loop.run_until_complete(get_response())
                return jsonify({'response': result})
                
            finally:
                loop.close()
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)})
    
    return app


def extract_sql(text: str) -> str:
    """暴力提取 SQL 语句"""
    text = text.strip()
    # 暴力提取：只要有 SELECT 就拿
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if line.upper().startswith('SELECT'):
            return line.rstrip(';') + ';'
    return ""


def escape_html(text):
    """转义 HTML"""
    if text is None:
        return ''
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#39;')


def generate_summary(question: str, df: pd.DataFrame, llm_service) -> str:
    """生成自然语言摘要"""
    try:
        if df.empty:
            return ""
        
        # 构建摘要请求
        sample_data = df.head(5).to_string()
        
        prompt = f"""根据以下数据分析和用户问题，给出简洁的自然语言总结。

用户问题: {question}

数据样本（前5条）:
{sample_data}

请用中文总结分析结果，不要超过3句话。"""
        
        # 同步调用
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        from vanna.core.llm import LlmRequest
        from vanna.core.user.models import User as VannaUser
        
        try:
            req = LlmRequest(
                messages=[{"role": "user", "content": prompt}],
                user=VannaUser(id="system", username="system")
            )
            response = loop.run_until_complete(llm_service.send_request(req))
            return response.content if response.content else ""
        finally:
            loop.close()
    except Exception as e:
        return ""


def generate_followup_questions(question: str, sql: str, df: pd.DataFrame, llm_service) -> List[str]:
    """生成追问建议"""
    try:
        if df.empty:
            return []
        
        sample_data = df.head(3).to_string()
        
        prompt = f"""基于以下查询和结果，给出5个可能的后续追问（每个问题不超过20字）。

当前问题: {question}
当前SQL: {sql}
查询结果:
{sample_data}

请直接返回5个问题，每行一个，不要编号。"""
        
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        from vanna.core.llm import LlmRequest
        from vanna.core.user.models import User as VannaUser
        
        try:
            req = LlmRequest(
                messages=[{"role": "user", "content": prompt}],
                user=VannaUser(id="system", username="system")
            )
            response = loop.run_until_complete(llm_service.send_request(req))
            
            questions = []
            for line in response.content.split('\n'):
                line = line.strip()
                if line and len(line) < 30:
                    questions.append(line)
            
            return questions[:5]
        finally:
            loop.close()
    except Exception as e:
        return []


def prepare_chart_data(df: pd.DataFrame, question: str) -> dict:
    """准备图表数据"""
    try:
        if df.empty or len(df) == 0:
            return None
        
        # 获取列名
        columns = df.columns.tolist()
        if len(columns) < 2:
            return None
        
        # 判断数据类型
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        string_cols = df.select_dtypes(include=['object']).columns.tolist()
        
        if not numeric_cols:
            return None
        
        # 确定标签列（优先使用字符串列，或第一列）
        label_col = string_cols[0] if string_cols else columns[0]
        
        # 确定数值列（最多取2个）
        value_cols = numeric_cols[:2]
        
        # 限制数据点数量（最多20个）
        max_points = 20
        df_subset = df.head(max_points)
        
        labels = df_subset[label_col].astype(str).tolist()
        
        datasets = []
        colors = [
            {'bg': 'rgba(230, 184, 0, 0.6)', 'border': 'rgba(230, 184, 0, 1)'},
            {'bg': 'rgba(0, 212, 255, 0.6)', 'border': 'rgba(0, 212, 255, 1)'},
            {'bg': 'rgba(124, 92, 224, 0.6)', 'border': 'rgba(124, 92, 224, 1)'},
            {'bg': 'rgba(255, 107, 53, 0.6)', 'border': 'rgba(255, 107, 53, 1)'}
        ]
        
        for i, col in enumerate(value_cols):
            color = colors[i % len(colors)]
            datasets.append({
                'label': col,
                'data': df_subset[col].tolist(),
                'backgroundColor': color['bg'],
                'borderColor': color['border'],
                'borderWidth': 2
            })
        
        # 智能推荐图表类型
        chart_type = 'bar'
        if len(df_subset) <= 10 and len(value_cols) == 1:
            chart_type = 'pie' if '占比' in question or '比例' in question else 'bar'
        elif len(df_subset) > 10:
            chart_type = 'line' if '趋势' in question or '变化' in question else 'bar'
        
        return {
            'type': chart_type,
            'labels': labels,
            'datasets': datasets,
            'title': question
        }
    except Exception as e:
        return None


if __name__ == '__main__':
    app = create_app()
    print("\n" + "="*60)
    print("🎮 Vanna SQL 智能助手启动成功!")
    print("   请访问: http://localhost:8080")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=8080, debug=True)
