# 智汇齐鲁·全域同频

智慧校园育人与生活服务平台的 Python/FastAPI 底座工程。

## 本地运行

```powershell
cd zhihui_qilu
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
python -m zhihui_qilu.main
```

服务启动后访问 `GET /healthz`。当前工程已经包含 Agent 底座、三层记忆、安全隔离以及五个业务模块的可运行参考实现。

## Web 客户端（开发阶段）

```powershell
cd web
npm install
npm run dev
```

前端开发服务器运行于 `http://localhost:5173`，并将 `/api` 代理到 FastAPI。开发身份通过请求头传递，仅用于本地演示；生产环境必须对接学校 SSO/JWT。

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

默认使用进程内存储，便于测试。将 `ZHQ_MEMORY_BACKEND=sqlite` 后，三层记忆会持久化至 `ZHQ_SQLITE_MEMORY_PATH`；容器编排已默认启用该模式并挂载数据卷。

## 功能覆盖说明

当前版本不是白皮书全部生产能力的最终交付版。界面只展示真实可调用能力，不使用虚构数据掩盖缺口。

已实现：

- 可拖动、可收起、带多种空闲动作的全身暖心引导员桌宠，以及 DeepSeek 多轮流式对话。
- 心情天气打卡、三档预警计算、隐私隔离、匿名寄语墙和辅导员寄语发布。
- 预置环境音、本地音乐导入、播放暂停、进度、音量、停止与清空。
- 文本课表解析、宿舍 AA 分摊、整改建议、日程冲突分析后端能力。
- DeepSeek 复试逐题追问、浏览器语音播报、可选语音识别、五维评估和转录文本结构化笔记。
- 学习成长功能选择页、独立笔记整理台和周计划生成器。
- 双创官方入口/演示学习资料信息流，以及右侧提交、组队、申报书和审核工具栏。
- 竞赛 UGC 提交、首发递减建议、管理员审核、技能匹配和申报书大纲。
- 公文要素提取、三层记忆、路由、安全网关和 SQLite 持久化。

仍需继续实现或接入：

- 辅导员预警总览、谈心预约工单和谈话台账导出完整前端流程。
- ICS、Excel、图片 OCR 课表上传界面，以及真实教务系统连接。
- 视频复试、服务端高精度语音识别、摄像头表情/姿态分析。
- 竞赛个性化推荐、官方群链接、积分账户、兑换、徽章与排行榜完整闭环。
- python-docx 文件导出、LaTeX/pdflatex 编译和 LLM 自修正生产链。
- 学校 SSO/JWT、心理中心、学工、教务等正式系统适配器。
