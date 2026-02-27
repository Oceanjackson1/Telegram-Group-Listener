<p align="center">
  <img src="https://img.shields.io/badge/Telegram-Bot-blue?logo=telegram&logoColor=white" />
  <img src="https://img.shields.io/badge/Python-3.9+-green?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/AI-DeepSeek-purple?logo=openai&logoColor=white" />
  <img src="https://img.shields.io/badge/License-MIT-yellow" />
</p>

<h1 align="center">🍉 Watermelon Monster</h1>
<p align="center"><b>一站式 Telegram 社区管理 AI Agent</b></p>
<p align="center">反垃圾 · 自动问答 · AI 知识库 · 活动抽奖 · 消息监控</p>

---

## 📖 目录

- [产品简介](#-产品简介)
- [核心功能](#-核心功能)
- [系统架构](#-系统架构)
- [快速开始](#-快速开始)
- [配置指南](#-配置指南)
- [命令一览](#-命令一览)
- [AI 知识库](#-ai-知识库)
- [目录结构](#-目录结构)
- [开发与测试](#-开发与测试)
- [部署方案](#-部署方案)
- [常见问题](#-常见问题)
- [License](#license)

---

## 🍉 产品简介

**Watermelon Monster** 是一款功能完整的 Telegram 社区管理 AI Agent。只需将 Bot 拉入群组，即可通过私聊后台完成所有配置——无需编写代码、无需额外后台。

它整合了 **6 大功能模块**，从基础的消息转发监控到 AI 驱动的智能对话，为社区运营者提供一站式管理工具。

### 适用场景

| 场景 | 示例 |
|------|------|
| 🏢 **项目方社区运营** | 管理代币/NFT 群，自动回答用户问题，过滤垃圾信息 |
| 📚 **知识社群** | 上传课程资料/文档，AI 根据内容自动答疑 |
| 🎮 **游戏/兴趣群** | 组织活动抽奖、自动发欢迎消息 |
| 📡 **信息监控** | 监控特定用户或关键词，实时转发到飞书/TG |

---

## ✨ 核心功能

### 模块 1：消息监控与转发
- 📡 **特定用户监控** — 追踪指定用户在群中的所有消息
- 🔎 **关键词监控** — 设定关键词，命中后自动转发
- 📮 **多目标转发** — 转发至 Telegram 群或飞书 Webhook
- 🌐 **双语支持** — 完整的中英文界面切换

### 模块 2：反垃圾 / 反 Spam
- 🚫 **关键词黑名单** — 自动删除包含敏感词的消息
- 🔗 **链接过滤** — 禁止外链，支持白名单域名
- 🔁 **刷屏检测** — 检测用户在短时间内重复发送相同消息
- ⚖️ **分级惩罚** — 删除、警告、禁言、踢出（可配置）
- ✅ **白名单用户** — 对信任用户免审

### 模块 3：自动问答 (Q&A)
- 💬 **精确匹配 / 模糊匹配** — 灵活的触发方式
- ⏱️ **冷却时间** — 防止同一规则被反复触发
- 📋 **群内 FAQ** — `/faq` 一键查看所有问答规则

### 模块 4：社群互动
- 👋 **欢迎消息** — 新成员加入时自动发送欢迎文案
- 🤖 **Bot 代发** — 管理员通过 Bot 在群里发消息
- 📝 **文案模板** — 支持 `{name}`、`{group}` 等变量

### 模块 5：活动与抽奖
- 🎉 **创建活动** — 设置标题、描述、奖品、截止时间
- 🎫 **一键参与** — 群内 Inline Button，用户点击即参加
- 🎰 **随机开奖** — 公平的随机抽奖算法，支持多名中奖
- 📢 **结果公示** — 自动公布中奖名单

### 模块 6：AI 知识库（DeepSeek 驱动）
- 📄 **文件上传** — 支持 PDF、TXT、MD、DOCX 格式
- 🧠 **智能检索** — BM25 算法匹配最相关知识片段
- 💡 **主动回答** — 监听群内所有消息，自动识别并回答问题
- 🎭 **Bot 人设** — 可自定义 System Prompt，打造专属 AI 角色
- 🔒 **速率控制** — 内置请求频率限制，防止 API 滥用

---

## 🏗 系统架构

```
┌──────────────────────────────────────────────────┐
│                  Telegram Bot API                 │
└───────────────────────┬──────────────────────────┘
                        │
          ┌─────────────┴─────────────┐
          │          bot.py           │
          │   (Handler 注册 & 路由)    │
          └─────────────┬─────────────┘
                        │
    ┌───────────────────┼───────────────────┐
    │                   │                   │
┌───┴────┐      ┌──────┴──────┐     ┌──────┴──────┐
│handlers│      │  services   │     │   utils     │
│ 消息处理│      │  业务逻辑    │     │  基础设施   │
└───┬────┘      └──────┬──────┘     └──────┬──────┘
    │                  │                   │
    │  ┌───────────────┼───────────┐       │
    │  │ antispam.py   │ qa.py     │       │
    │  │ events.py     │ community │       │
    │  │ deepseek.py   │ ai_chat   │       │
    │  │ knowledge.py  │ file_parser│      │
    │  └───────────────┴───────────┘       │
    │                                      │
    └──────────────┬───────────────────────┘
                   │
          ┌────────┴────────┐
          │   SQLite DB     │
          │  data/bot.db    │
          └─────────────────┘
```

### 消息处理优先级

```
群消息 → ① 反垃圾检测（最高优先级）
       → ② 自动问答匹配
       → ③ AI 知识库回答
       → ④ 消息监控转发
       → ⑤ 新成员欢迎
```

---

## 🚀 快速开始

### 环境要求

- Python 3.9+
- Telegram Bot Token（从 [@BotFather](https://t.me/BotFather) 获取）
- DeepSeek API Key（可选，用于 AI 功能）

### 1. 克隆项目

```bash
git clone https://github.com/your-username/watermelon-monster.git
cd watermelon-monster
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

依赖清单：
| 包名 | 用途 |
|------|------|
| `python-telegram-bot` | Telegram Bot API |
| `httpx` | HTTP 请求（飞书 Webhook / DeepSeek API） |
| `python-dotenv` | 环境变量管理 |
| `PyPDF2` | PDF 文件解析 |
| `python-docx` | DOCX 文件解析 |

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`：

```env
# 必填 — Telegram Bot Token
BOT_TOKEN=your_telegram_bot_token_here

# 可选 — AI 知识库功能需要
DEEPSEEK_API_KEY=sk-your_deepseek_api_key_here
```

### 4. 数据迁移（仅旧用户）

如果你之前使用过旧版（JSON 配置），运行迁移脚本：

```bash
python scripts/migrate_json_to_sqlite.py
```

### 5. 启动 Bot

```bash
python bot.py
```

---

## ⚙️ 配置指南

所有配置均通过 **Telegram 私聊** 完成，无需修改任何文件。

### 消息监控配置（`/start` 或 `/config`）

1. 选择语言
2. 选择监控模式（特定人员 / 关键词）
3. 设置来源群组和目标
4. 设置转发目的地（飞书 Webhook / Telegram 群）
5. 确认并启动

### 社区管理配置（`/admin`）

在 **私聊** 中发送 `/admin`，进入管理面板：

```
📊 管理面板
├── 选择群组
│   ├── 🛡️ 反垃圾
│   │   ├── 启用/关闭
│   │   ├── 关键词黑名单
│   │   ├── 链接过滤
│   │   ├── 惩罚方式
│   │   └── 白名单用户
│   ├── 💬 自动问答
│   │   ├── 添加规则
│   │   ├── 查看全部
│   │   └── 清空
│   ├── 👋 社群互动
│   │   ├── 欢迎消息
│   │   └── Bot 代发
│   ├── 🎉 活动抽奖
│   │   ├── 创建活动
│   │   ├── 查看活动
│   │   └── 开奖
│   └── 🧠 AI 知识库
│       ├── 上传知识文件
│       ├── 查看已上传文件
│       ├── Bot 人设设定
│       └── 使用统计
```

---

## 📋 命令一览

### 私聊命令

| 命令 | 描述 |
|------|------|
| `/start` | 启动 Bot，进入配置流程 |
| `/config` | 重新配置消息监控 |
| `/admin` | 打开社区管理面板 |
| `/status` | 查看当前监控状态 |
| `/stop` | 停止所有监控 |
| `/lang` | 切换语言（中/英） |
| `/help` | 查看帮助 |

### 群内命令

| 命令 | 描述 |
|------|------|
| `/faq` | 查看本群所有 Q&A 规则 |
| `/ask <问题>` | 向 AI 知识库提问 |
| `/events` | 查看本群进行中的活动 |

### 隐式交互

| 触发方式 | 行为 |
|---------|------|
| 新成员加入 | 自动发送欢迎消息 |
| @Bot + 问题 | AI 回答 |
| 群内提问（含问号等） | AI 智能识别并主动回答 |
| 点击"参加抽奖"按钮 | 加入活动 |

---

## 🧠 AI 知识库

### 工作原理

```
管理员上传文件 → 文本提取 → 分片存储（~800字/片）→ 关键词索引
                                                        ↓
群内用户提问 → 问题检测 → BM25 检索匹配 → 构建提示词 → DeepSeek API → 回复
```

### 支持的文件格式

| 格式 | 说明 | 大小限制 |
|------|------|---------|
| `.pdf` | PDF 文档 | 10MB |
| `.txt` | 纯文本 | 10MB |
| `.md` | Markdown 文档 | 10MB |
| `.docx` | Word 文档 | 10MB |

### AI 触发模式

| 模式 | 说明 |
|------|------|
| `all`（默认） | 监听所有消息，检测到问句自动回答 |
| `mention` | 仅在 @Bot 时回答 |
| `keyword` | 消息包含指定关键词时回答 |

### API 保护机制

- **请求频率限制** — 每群每分钟最多 10 次请求
- **并发控制** — 最多 5 个并发 API 请求
- **重试机制** — 失败自动重试 3 次，指数退避
- **Token 限制** — 单次回复最多 1024 tokens

---

## 📁 目录结构

```
watermelon-monster/
├── bot.py                    # 入口文件，注册所有 Handler
├── requirements.txt          # Python 依赖
├── Dockerfile                # Docker 构建
├── .env.example              # 环境变量模板
│
├── handlers/                 # 消息处理层
│   ├── admin.py              #   /admin 管理面板（29 状态 ConversationHandler）
│   ├── antispam.py           #   反垃圾消息拦截
│   ├── qa.py                 #   自动问答匹配 + /faq
│   ├── ai_chat.py            #   AI 智能回答 + /ask
│   ├── community.py          #   欢迎消息 + Bot 注册
│   ├── events.py             #   活动参与/开奖 + /events
│   ├── commands.py           #   基础命令 (/help, /status, /stop, /lang)
│   ├── config.py             #   监控配置流程
│   ├── monitor.py            #   消息转发逻辑
│   └── start.py              #   /start 初始化
│
├── services/                 # 业务逻辑层
│   ├── antispam.py           #   垃圾检测引擎
│   ├── qa.py                 #   Q&A 匹配引擎
│   ├── community.py          #   欢迎消息格式化
│   ├── events.py             #   活动 CRUD + 抽奖算法
│   ├── deepseek.py           #   DeepSeek API 客户端
│   ├── file_parser.py        #   文件解析（PDF/TXT/MD/DOCX）
│   ├── knowledge.py          #   知识库存储 + BM25 检索
│   ├── ai_chat.py            #   AI 对话引擎（记忆 + 上下文）
│   ├── lark.py               #   飞书 Webhook 推送
│   └── telegram.py           #   Telegram 消息转发
│
├── utils/                    # 基础设施层
│   ├── database.py           #   SQLite 数据库（15 张表）
│   ├── group_manager.py      #   群组注册 + 管理员管理
│   ├── config_store.py       #   JSON 配置读写（旧版兼容）
│   ├── i18n.py               #   国际化
│   ├── validators.py         #   输入校验
│   └── logger.py             #   日志配置
│
├── i18n/                     # 多语言文件
│   ├── en.json               #   英文（170+ 条）
│   └── zh.json               #   中文（170+ 条）
│
├── scripts/                  # 工具脚本
│   └── migrate_json_to_sqlite.py  # JSON → SQLite 迁移
│
├── tests/                    # 测试
│   └── test_all.py           #   73 个自动化测试
│
└── data/                     # 运行时数据（自动创建）
    ├── bot.db                #   SQLite 数据库
    └── uploads/              #   上传文件存储
        └── <chat_id>/
```

---

## 🧪 开发与测试

### 运行测试

```bash
python -m pytest tests/test_all.py -v
```

测试覆盖 12 个模块，73 个测试用例：

| 模块 | 测试数 | 覆盖内容 |
|------|--------|---------|
| Database | 6 | Schema 创建、CRUD |
| GroupManager | 7 | 群组注册、管理员、语言 |
| AntiSpam | 10 | 黑名单、链接、刷屏、白名单 |
| Q&A | 6 | 模糊/精确匹配、冷却 |
| Events | 8 | 加入/去重、开奖、多人中奖 |
| FileParser | 8 | 文件解析、分片、关键词 |
| Knowledge | 6 | BM25 检索、存储、删除 |
| AI Chat | 9 | 意图识别、记忆、触发模式 |
| Community | 3 | 欢迎消息格式化 |
| i18n | 6 | 中英文 key 完整性 |
| Migration | 2 | JSON 迁移 |
| DeepSeek | 2 | API 调用、频率限制 |

---

## 🐳 部署方案

### 方案 1：Docker（推荐）

```bash
# 构建镜像
docker build -t watermelon-monster .

# 运行
docker run -d \
  --name watermelon-monster \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  watermelon-monster
```

### 方案 2：直接运行

```bash
# 后台运行
nohup python bot.py > bot.log 2>&1 &
```

### 方案 3：Systemd 服务

```ini
# /etc/systemd/system/watermelon-monster.service
[Unit]
Description=Watermelon Monster Telegram Bot
After=network.target

[Service]
Type=simple
User=bot
WorkingDirectory=/opt/watermelon-monster
ExecStart=/opt/watermelon-monster/venv/bin/python bot.py
Restart=always
RestartSec=10
EnvironmentFile=/opt/watermelon-monster/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable watermelon-monster
sudo systemctl start watermelon-monster
```

---

## 🔐 安全须知

- ⚠️ **不要将 `.env` 提交到版本控制**（已在 `.gitignore` 中排除）
- 🔑 DeepSeek API Key 请妥善保管
- 🛡️ Bot Token 泄露应立即在 @BotFather 中 Revoke
- 📦 数据库文件 `data/bot.db` 包含用户数据，注意备份

---

## ❓ 常见问题

<details>
<summary><b>Q: Bot 在群里没有反应？</b></summary>

1. 确认 Bot 已被添加为群管理员（反垃圾功能需要删除消息权限）
2. 确认发送了 `/admin` 并选择了该群进行配置
3. 检查是否启用了对应模块（反垃圾/Q&A/AI 默认关闭，需手动开启）
</details>

<details>
<summary><b>Q: AI 不回答问题？</b></summary>

1. 检查 `.env` 中是否配置了 `DEEPSEEK_API_KEY`
2. 在 `/admin → AI 知识库` 中确认已启用
3. 确认已上传至少一个知识文件
4. 默认模式为 `all`（自动识别问句），试试发送带 `?` 的消息
</details>

<details>
<summary><b>Q: 如何从旧版本迁移？</b></summary>

运行 `python scripts/migrate_json_to_sqlite.py`，会将 `user_configs.json` 中的监控配置自动导入 SQLite。
</details>

<details>
<summary><b>Q: 支持哪些 Python 版本？</b></summary>

Python 3.9+。推荐 3.11（Docker 镜像默认使用 3.11）。
</details>

---

## 📄 License

MIT License — 自由使用、修改、分发。

---

<p align="center">
  <b>🍉 Watermelon Monster</b> — 让社区管理变得简单
</p>
