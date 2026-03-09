# Notion AI API Wrapper - 项目进展与架构说明

**最后更新**: 2026-03-09 08:46

## 📋 项目概述

Notion AI API Wrapper 是一个基于 FastAPI 的反向工程项目，通过逆向 Notion Web API 实现 OpenAI 兼容的对话接口。项目核心目标是提供稳定、高效的 AI 对话服务，同时具备完善的对话历史管理和多账号负载均衡能力。

### 核心特性

- 🔄 **OpenAI 兼容接口** - 标准 Chat Completion API 格式
- 💬 **流式响应** - SSE 实时输出，支持思考过程展示
- 🧠 **分层记忆系统** - 滑动窗口 + 压缩池 + 全量归档
- 🔍 **智能召回** - 自然语言检索历史对话
- 👥 **账号池管理** - 多账号负载均衡与故障转移
- 🔐 **API Key 鉴权** - 可选的安全验证
- ⚡ **速率限制** - 内置请求频率控制
- 🎨 **Web 界面** - 简洁的聊天前端
- 🐳 **Docker 支持** - 完整容器化部署方案

---

## 🎯 重大里程碑：v0.9 版本（2026-03-09）

### 问题背景

项目在早期版本存在严重的**上下文记忆缺失问题**：AI 无法回忆之前的对话内容，每次请求都像第一次对话。经过深入分析，发现根本原因是：

1. **Thread ID 管理缺陷** - 每次请求创建新 thread，无法保持对话上下文
2. **Thread 自动删除** - 请求结束后立即删除 thread，服务器端丢失历史
3. **Notion API 参数错误** - `is_partial_transcript=false` 导致 Notion 忽略客户端历史

### 核心修复方案

#### 1. **Thread ID 持久化与复用机制**

**实现位置**: `app/conversation.py`

```python
# 数据库 schema 修改
ALTER TABLE conversations ADD COLUMN thread_id TEXT;

# 新增方法
def get_conversation_thread_id(conversation_id: str) -> Optional[str]
def set_conversation_thread_id(conversation_id: str, thread_id: str) -> None
```

**工作原理**:
- 首次请求：创建新 thread_id 并保存到数据库
- 后续请求：从数据库读取并重用同一个 thread_id
- 确保 Notion 服务器端识别为同一对话

#### 2. **移除 Thread 自动删除逻辑**

**实现位置**: `app/notion_client.py`

**修改前**:
```python
# 每次请求后立即删除 thread
threading.Thread(target=self.delete_thread, args=(thread_id,)).start()
```

**修改后**:
```python
# 完全移除自动删除，保留 thread 存活
logger.info("Thread completed and preserved for conversation context")
```

**权衡**:
- ✅ 优点：维持 Notion 服务器端对话状态
- ❌ 副作用：Notion 主页会累积对话记录（可接受）

#### 3. **关键修复：is_partial_transcript=True**

**实现位置**: `app/notion_client.py`

```python
def stream_response(self, transcript: list, thread_id: Optional[str] = None):
    # 第一轮：新对话
    if should_create_thread:
        request_profile["is_partial_transcript"] = False

    # 第二轮及以后：重用 thread
    else:
        request_profile["create_thread"] = False
        request_profile["is_partial_transcript"] = True  # ← 关键修复
```

**为什么这个参数如此重要？**

`is_partial_transcript` 参数告诉 Notion API 如何处理客户端发送的 transcript：

- **`False`（完整模式）**: Notion 忽略 transcript 中的历史消息，只依赖服务器端状态
- **`True`（部分模式）**: Notion 接受并使用 transcript 中的历史消息

这是解决 AI 失忆问题的**最关键修复**！

#### 4. **移除 Legacy 回退逻辑**

**实现位置**: `app/conversation.py` - `get_transcript_payload()`

**修改前**:
```python
if sliding_window_rounds > 0:
    recent_messages = self.get_sliding_window(conn, conversation_id)
else:
    # 回退到旧的 messages 表
    recent_messages = self._fetch_recent_messages(conn, conversation_id)
    recent_messages = self._normalize_window_messages(recent_messages)
```

**修改后**:
```python
# 强制使用滑动窗口作为唯一数据源
recent_messages = self.get_sliding_window(conn, conversation_id)
```

**原因**: 新老逻辑混用导致数据源不一致，造成上下文断裂

#### 5. **滑动窗口数据完整性优化**

**实现位置**: `app/conversation.py` - `persist_round()`, `update_sliding_window()`

**修改**:
- `INSERT OR IGNORE` → `INSERT ... ON CONFLICT DO UPDATE SET` (UPSERT)
- 移除 `update_sliding_window()` 的提前返回检查
- 确保数据幂等性和完整性

### 验证结果

✅ **测试通过**: AI 能正确回忆之前的对话内容
✅ **多轮对话**: 保持上下文连贯性（0→2→4→6 条消息累积）
✅ **Thread 复用**: 整个对话使用同一个 thread_id
✅ **参数正确**: `is_partial_transcript=true` 在后续轮次中正确设置

---

## 🏗️ 技术架构演进

### 记忆系统架构（三层设计）

```
┌─────────────────────────────────────────────────────────┐
│                    应用层 (Application)                  │
│  - OpenAI 兼容 API                                        │
│  - 流式响应处理                                           │
│  - 前端界面                                               │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                  记忆管理层 (Memory)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ 滑动窗口表    │  │ 压缩摘要表    │  │ 全量归档表    │  │
│  │ sliding_window│  │compressed_   │  │ full_archive │  │
│  │ (8轮对话)     │  │ summaries    │  │ (永久存储)   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                 持久化层 (Storage)                       │
│  - SQLite3 数据库                                        │
│  - Thread ID 管理                                        │
│  - 对话元数据                                            │
└─────────────────────────────────────────────────────────┘
```

### 消息流程（v0.9 版本）

```
用户请求
    ↓
chat.py (API 层)
    ↓
conversation.py (记忆管理层)
    ├── 读取 thread_id
    ├── 构建滑动窗口历史 (get_sliding_window)
    ├── 添加压缩摘要 (如果有)
    └── 构建 transcript
    ↓
notion_client.py (Notion API 客户端)
    ├── 复用 thread_id
    ├── 设置 is_partial_transcript=true
    └── 发送请求到 Notion
    ↓
Notion 服务器
    ├── 接收 transcript + thread_id
    ├── 使用 transcript 中的历史消息
    └── 调用 AI 模型生成回复
    ↓
返回给用户
```

### 关键设计决策

#### 为什么使用滑动窗口而不是全量历史？

1. **性能考虑** - 减少每次请求的数据传输量
2. **成本控制** - Notion API 有 token 限制
3. **上下文质量** - 最近的历史更相关，过度久远的内容可能引入噪音
4. **压缩机制** - 通过摘要保留长期记忆的关键信息

#### 为什么需要 is_partial_transcript=True？

Notion API 的 workflow 模式设计：
- 完整模式（`false`）: 适用于全新对话，Notion 会忽略客户端历史
- 部分模式（`true`）: 适用于对话延续，Notion 会使用客户端提供的历史

**这是 Notion API 的特殊行为，需要客户端明确告知！**

---

## 📊 当前状态

### 已实现功能

| 功能模块 | 状态 | 说明 |
|---------|------|------|
| OpenAI 兼容 API | ✅ 完成 | 支持 Chat Completion 格式 |
| 流式响应 | ✅ 完成 | SSE 实时输出 |
| 滑动窗口 | ✅ 完成 | 8 轮对话窗口 |
| 压缩池 | ✅ 完成 | 自动摘要长期记忆 |
| 全量归档 | ✅ 完成 | 永久存储所有对话 |
| 记忆召回 | ✅ 完成 | 自然语言检索历史 |
| Thread 管理 | ✅ 完成 | v0.9 新增 |
| 账号池 | ✅ 完成 | 多账号负载均衡 |
| 速率限制 | ✅ 完成 | IP 级别频率控制 |
| API Key 鉴权 | ✅ 完成 | 可选安全验证 |
| Web 界面 | ✅ 完成 | 单页面应用 |
| Docker 部署 | ✅ 完成 | 完整容器化 |

### 数据库 Schema

```sql
-- 对话表
conversations (
    id TEXT PRIMARY KEY,
    title TEXT,
    created_at INTEGER,
    next_round_index INTEGER,
    thread_id TEXT,              -- v0.9 新增
    summary TEXT,
    compress_failed_at INTEGER
)

-- 滑动窗口表（核心记忆）
sliding_window (
    id INTEGER PRIMARY KEY,
    conversation_id TEXT,
    round_number INTEGER,         -- 轮次号
    user_content TEXT,            -- 用户消息
    assistant_content TEXT,       -- 助手回复
    assistant_thinking TEXT,      -- 思考过程
    compress_status TEXT,         -- 压缩状态
    created_at INTEGER,
    UNIQUE(conversation_id, round_number)
)

-- 压缩摘要表（中期记忆）
compressed_summaries (
    id INTEGER PRIMARY KEY,
    conversation_id TEXT,
    round_index INTEGER,
    user_content TEXT,
    assistant_content TEXT,
    summary TEXT,
    compress_status TEXT,
    created_at INTEGER
)

-- 全量归档表（长期记忆）
full_archive (
    id INTEGER PRIMARY KEY,
    conversation_id TEXT,
    role TEXT,
    content TEXT,
    round_index INTEGER,
    created_at INTEGER,
    UNIQUE(conversation_id, round_index, role, content)
)

-- 消息表（兼容性保留）
messages (
    id INTEGER PRIMARY KEY,
    conversation_id TEXT,
    role TEXT,
    content TEXT,
    thinking TEXT,
    created_at INTEGER
)
```

### 支持的模型

| 模型名称 | Notion 内部标识 | 特点 |
|---------|----------------|------|
| claude-opus4.6 | avocado-froyo-medium | Opus 4.6，最强推理能力 |
| claude-sonnet4.6 | almond-croissant-low | Sonnet 4.6，平衡性能 |
| gemini-3.1pro | galette-medium-thinking | Gemini 3.1 Pro |
| gpt-5.2 | oatmeal-cookie | GPT-5.2 |
| gpt-5.4 | oval-kumquat-medium | GPT-5.4，最新版本 |

---

## 🚀 未来发展方向

### 短期目标（v1.0）

1. **Thread 自动清理机制**
   - 问题：当前 Notion 主页会累积对话记录
   - 方案：实现定期清理逻辑（如 24 小时后自动删除）
   - 优先级：中

2. **记忆压缩优化**
   - 当前：简单的文本摘要
   - 改进：使用 AI 模型生成更高质量的摘要
   - 优先级：中

3. **监控和可观测性**
   - 添加 Prometheus metrics
   - 实现健康检查增强
   - 添加性能监控面板
   - 优先级：低

### 中期目标（v1.1+）

1. **多模态支持**
   - 图片输入/输出
   - 文件处理能力
   - 优先级：待定

2. **Function Calling**
   - 工具调用能力
   - 外部 API 集成
   - 优先级：待定

3. **分布式部署**
   - Redis 缓存层
   - 数据库主从复制
   - 优先级：待定

### 长期愿景

1. **插件系统**
   - 可扩展的插件架构
   - 社区贡献插件

2. **多语言支持**
   - 国际化前端
   - 多语言模型切换

3. **企业级特性**
   - 多租户支持
   - RBAC 权限控制
   - 审计日志

---

## ⚠️ 已知问题和限制

### 当前限制

1. **Notion 主页累积**
   - 问题：对话记录不会被自动删除
   - 影响：Notion 主页会显示大量历史对话
   - 解决方案：手动清理或等待 v1.0 自动清理功能

2. **模型限制**
   - 依赖 Notion 提供的模型
   - 无法自定义模型参数
   - 无法使用本地模型

3. **并发限制**
   - 单机部署，受限于 Python GIL
   - 高并发场景建议使用多进程部署

### 注意事项

⚠️ **安全警告**
- 不要分享 `token_v2`，它等同于你的 Notion 账号密码
- 建议在生产环境使用 API Key 鉴权
- 定期更新 token_v2 以避免过期

⚠️ **法律风险**
- 本项目仅用于学习和研究目的
- 请遵守 Notion 的服务条款
- 避免频繁请求以免触发 Notion 的限流机制
- 商业使用需自行承担法律责任

---

## 📚 开发指南

### 快速开始

```bash
# 1. 克隆项目
git clone <repository-url>
cd notion-ai

# 2. 安装依赖
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. 配置环境
cp .env.example .env
# 编辑 .env 文件，填写 Notion 账号信息

# 4. 启动服务
uvicorn app.server:app --reload --host 0.0.0.0 --port 8000
```

### 核心代码说明

| 文件 | 作用 | 关键类/函数 |
|------|------|------------|
| `app/server.py` | FastAPI 应用入口 | `app`, `lifespan` |
| `app/api/chat.py` | 聊天 API 路由 | `create_chat_completion()` |
| `app/conversation.py` | 对话历史管理 | `ConversationManager` |
| `app/notion_client.py` | Notion API 客户端 | `NotionClient.stream_response()` |
| `app/account_pool.py` | 账号池管理 | `AccountPool` |
| `app/model_registry.py` | 模型注册表 | `get_standard_model()` |

### 测试

```bash
# 运行单元测试
pytest tests/

# 运行集成测试
python final_test.py

# 手动测试
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-5.4", "messages": [{"role": "user", "content": "你好"}]}'
```

---

## 📝 更新日志

### v0.9 (2026-03-09)

**重大修复**: 上下文记忆缺失问题

- ✅ 实现 Thread ID 持久化与复用
- ✅ 移除 Thread 自动删除逻辑
- ✅ 添加 `is_partial_transcript=True` 支持
- ✅ 移除 Legacy 回退逻辑
- ✅ 优化滑动窗口数据完整性
- ✅ 添加详细调试日志

**验证**: AI 能够正确回忆之前的对话内容，多轮对话保持上下文连贯

### v1.0.0 (2025-03-06)

- 初始版本发布
- 支持 OpenAI 兼容的 Chat Completion API
- 实现流式响应
- 添加对话历史管理
- 支持记忆召回功能
- 实现账号池管理
- 添加 Docker 部署支持

---

## 🙏 致谢

感谢所有为这个项目做出贡献的开发者。特别感谢：

- Notion AI 团队提供的优秀 AI 服务
- OpenAI 团队制定的 API 标准
- Claude (Anthropic) 在开发和调试过程中提供的帮助

---

## 📄 许可证

本项目仅供学习交流使用。请遵守 Notion 的服务条款和相关法律法规。

---

**文档版本**: v0.9
**最后更新**: 2026-03-09 08:46
**维护者**: Maverickxone
**贡献**: 欢迎提交 Issue 和 Pull Request
