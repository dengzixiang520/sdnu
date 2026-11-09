# 智汇齐鲁·全域同频

智慧校园育人与生活服务平台的 Python/FastAPI 底座工程。

## 一键启动（推荐，答辩现场用这个）

参赛包根目录的 `启动.bat` 是唯一入口：自动准备便携版 Python 3.11.9 与 Node 20.18.0、补齐依赖、启动前后端并打开浏览器，全部装在 `code/runtime/` 内，不写注册表、不改系统 PATH，整个文件夹可直接拷贝到另一台机器。

```text
启动.bat             双击运行；前端 http://localhost:5173 ，接口文档 http://127.0.0.1:8000/docs
重置演示数据.bat      把积分/兑换/课表/记忆恢复到干净的演示基线（反复排练后用）
```

## 本地运行（开发）

```powershell
cd code
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
python -m zhihui_qilu.main
```

服务启动后访问 `GET /healthz`。

## Web 客户端（开发阶段）

```powershell
cd web
npm install
npm run dev
```

前端开发服务器运行于 `http://localhost:5173`，并将 `/api` 代理到 FastAPI。开发身份通过请求头传递，仅用于本地演示；生产环境必须对接学校 SSO/JWT。

## 测试

```powershell
python -m pytest -q
```

覆盖安全网关、三层记忆作用域、五个业务 Skill、数据导出与计分账目等回归项。

## DeepSeek 对话配置

暖心引导员和 AI 模拟复试共用可替换的大模型适配层。请先复制环境文件，再把**新申请且未公开过**的密钥写进本机 `.env`，不要写进前端、源码或提交记录：

```powershell
Copy-Item .env.example .env
# 编辑 .env
ZHQ_AI_PROVIDER=deepseek
ZHQ_AI_BASE_URL=https://api.deepseek.com
ZHQ_AI_MODEL=deepseek-chat
ZHQ_AI_API_KEY=your-rotated-key
```

修改配置后重启 FastAPI。没有配置密钥时，系统会进入可测试的本地兜底模式，并在导航员对话框中明确标注，不会伪装成在线模型。

## 记忆持久化

`ZHQ_MEMORY_BACKEND` 支持两种后端：

- `sqlite`（**参赛包默认**）：三层记忆持久化至 `ZHQ_SQLITE_MEMORY_PATH`，重启进程后对话上下文、心情打卡与预警记录仍在；`compose.yaml` 已默认启用并挂载数据卷。
- `memory`：进程内存储，每次启动都是干净状态，便于自动化测试与可重复的演示排练。

两种后端实现同一个 `MemorySystem` 端口，切换只需改一行配置。

## 功能覆盖说明

当前版本不是白皮书全部生产能力的最终交付版。界面只展示真实可调用能力，不使用虚构数据掩盖缺口。

已实现：

- 可拖动、可收起、带多种空闲动作的全身暖心引导员桌宠，以及 DeepSeek 多轮流式对话。
- 心情天气打卡、三档预警计算、隐私隔离、匿名寄语墙和辅导员寄语发布。
- 辅导员预警总览（跨学生查询，且预警记录在类型层不允许携带对话原文）与谈心台账导出（TXT / CSV / PDF）。
- 预置环境音、本地音乐导入、播放暂停、进度、音量、停止与清空。
- 课表解析：文本、CSV、Excel（.xlsx/.xls）、ICS 日历；PDF 解析返回明确的 501 而非静默失败。
- 宿舍 AA 分摊（按分精确结算）、整改建议、日程冲突分析后端能力。
- DeepSeek 复试逐题追问、浏览器语音播报、可选语音识别、五维评估和转录文本结构化笔记。
- 学习成长功能选择页、独立笔记整理台和周计划生成器。
- 双创官方入口/演示学习资料信息流，以及右侧提交、组队、申报书和审核工具栏。
- 竞赛 UGC 提交、首发递减建议、管理员审核、技能匹配和申报书大纲。
- 积分中心：打卡计分、竞赛积分、等级与徽章、排行榜、积分兑换商城（服务端并发加锁，不会超卖或超扣）。
- 公文要素提取（DOCX 导出返回真实文件）、三层记忆、路由、安全网关和 SQLite 持久化。

仍需继续实现或接入：

- 视频复试、服务端高精度语音识别、摄像头表情/姿态分析。
- 真实教务系统、心理中心、学工等正式系统的数据适配器（当前 `system_integration` 为占位实现，接口已定义、数据为演示值）。
- 学校 SSO/JWT 单点登录（当前开发身份通过请求头传递）。
- LaTeX/pdflatex 编译与 LLM 自修正生产链。

## 目录

```text
src/zhihui_qilu/
├── core/        安全网关、领域模型、枚举、错误
├── memory/      三层记忆端口与 memory / sqlite 两个实现
├── ai/          大模型适配层（DeepSeek / 离线兜底）与会话服务
├── agents/      SuperAgentRouter（L1 直连路由 + L2 规划桩）
├── skills/      五个业务能力（暖心 / 宿舍 / 学业 / 创新 / 公文）
├── api/         FastAPI 应用、依赖与路由
└── data/        业务数据（竞赛库、商品、积分、课表）
```
