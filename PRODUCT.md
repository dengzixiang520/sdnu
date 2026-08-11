# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- Primary: 山东师范大学及同类高校的在校学生，在课业、生活、心理支持与竞赛成长之间切换，希望少找入口、少重复描述、获得连续帮助。
- Secondary: 辅导员与平台管理员，只在明确授权和最小必要范围内处理寄语、关怀提醒、谈心台账与竞赛审核。

## Product Purpose

“智汇齐鲁·全域同频”把校园育人和生活服务组织成一个多 Agent 协同平台。成功不是展示更多 AI 卡片，而是让学生先看懂当下可以做什么，再进入一个专注、可信且能保留上下文的工作流。

## Positioning

平台以统一安全网关和三层记忆连接暖心陪伴、宿舍协同、学习成长、双创孵化与文档规范化；各模块保持独立任务语言，但可以在用户授权下共享必要上下文。

## Operating Context

- 学生在电脑和手机浏览器中完成心情打卡、陪伴对话、日程协同、模拟复试、笔记整理、竞赛发现和申报准备。
- 全局左侧导航负责平台级切换；模块内部通过主内容区与右侧工具轨组织浏览和操作。
- 暖心引导员是可拖动的全身桌面伙伴，支持多轮对话、空闲动作和明确的隐私边界。
- 真实学校通知、竞赛信息和资源必须标注来源；没有接入官方数据源时不得伪装成实时官方信息。

## Capabilities and Constraints

- Existing stack: FastAPI, Python 3.11+, Vue 3, TypeScript and Vite.
- LLM provider uses an adapter boundary. DeepSeek is the first provider; keys live only in environment configuration.
- High-risk wellbeing detection, permission checks, prompt-injection screening and PII redaction remain deterministic and outside the LLM.
- Browser SpeechSynthesis is the immediate voice-questioning fallback. Microphone capture requires explicit browser permission and a future STT provider.
- Development headers are not production authentication. Production SSO, school systems and psychological-center adapters remain explicit integration work.

## Brand Commitments

- Name: “智汇齐鲁·全域同频”.
- Required reference: the hover-expand sidebar and interaction clarity of the supplied “心理agent” project, adapted rather than copied mechanically.
- Voice: warm, direct, respectful and campus-native; avoid bureaucratic slogans, diagnostic claims and generic AI marketing language.
- Each module must visibly express its own purpose instead of reusing an identical card template.

## Evidence on Hand

- Technical whitepaper: `C:\Users\x\Desktop\智汇齐鲁-全域同频-技术白皮书-V2答辩优化版.md`.
- Reference implementation: `D:\study-race\race\中国高校计算机\心理agent\中国高校计算机\same_wavelength\dashboard`.
- Existing runnable backend, frontend and automated tests in this repository.
- No verified live school-notice feed, campus SSO credential, psychological appointment API or production AI key is committed. Future UI must not fabricate these integrations.

## Product Principles

1. 先任务后技术：页面首先帮助学生完成事情，Agent 架构退居幕后。
2. 模块同根不同貌：全局导航和安全规则统一，模块工作台按真实任务重新组织。
3. 陪伴不越界：引导员可以温暖、灵动，但不冒充心理医生，不替代紧急支持和人工辅导。
4. 真实来源优先：官方内容标来源，演示数据明确标注，未知能力不假装已接入。
5. 可控、可停、可撤回：音乐、语音、记忆和 AI 请求都提供清晰控制与错误恢复。

## Accessibility & Inclusion

- 正文字号和对比度适合长时间阅读，关键文字不低于 14px。
- 所有核心流程支持键盘焦点、清晰标签、减少动态偏好和移动端布局。
- 动画表达状态而非制造压力；高风险提示使用文字与结构，不仅依赖颜色。
