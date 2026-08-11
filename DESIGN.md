---
name: 智汇齐鲁·全域同频
description: 一张可展开、可陪伴、可持续工作的齐鲁校园阅读桌
colors:
  ink: "#172b2a"
  muted: "#667572"
  canvas: "#eef1ea"
  paper: "#fffef8"
  paper-soft: "#f5f4eb"
  spine-green: "#173f43"
  action-green: "#397f72"
  calm-green: "#dfece5"
  coral: "#d8614d"
  warm-gold: "#d6a849"
  divider: "#d8ded4"
  danger: "#b63d3d"
typography:
  display:
    fontFamily: '"LXGW WenKai", "STKaiti", "KaiTi", serif'
    fontSize: "clamp(2.35rem, 4.8vw, 4.8rem)"
    fontWeight: 400
    lineHeight: 1.05
  body:
    fontFamily: '"Noto Sans SC Variable", "Microsoft YaHei", sans-serif'
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.7
  label:
    fontFamily: '"Noto Sans SC Variable", "Microsoft YaHei", sans-serif'
    fontSize: "0.8rem"
    fontWeight: 700
    lineHeight: 1.4
rounded:
  control: "10px"
  surface: "18px"
  feature: "26px"
spacing:
  xs: "6px"
  sm: "10px"
  md: "18px"
  lg: "24px"
  xl: "34px"
components:
  button-primary:
    backgroundColor: "{colors.action-green}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  input:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "11px 13px"
---

# Design System: 智汇齐鲁·全域同频

## Overview

**Creative North Star: “齐鲁校园阅读桌”**

界面不是一排同款 AI 卡片，而是一张随着任务展开的校园阅读桌：左侧像书脊一样负责平台切换，中间是当前真正要做的事，右侧收纳声音、组队、申报等上下文工具。暖心空间柔和可呼吸，复试空间像安静候考室，双创空间像校园情报站，各模块同根但不复制布局。

系统应显得温暖、可信、利索。AI 退居任务之后；真实来源、隐私边界、停止按钮和恢复路径必须比“智能感”更醒目。

**Key Characteristics:** 墨绿书脊导航、纸张感内容面、书写感标题、模块专属工作台、克制的状态动画、可拖动全身引导员。

## Colors

主色来自墨绿、宣纸白与旧书暖黄；珊瑚红只用于行动和双创强调，危险红只表达风险。

- **书脊墨绿** (`#173f43`)：平台导航、深色操作区和稳定锚点。
- **行动暖绿** (`#397f72`)：主要按钮、对话气泡和选中状态。
- **纸张白** (`#fffef8`) 与 **纸张灰** (`#f5f4eb`)：阅读和表单表面。
- **珊瑚朱红** (`#d8614d`)：重点动作、双创语境和焦点提示。
- **旧书暖黄** (`#d6a849`)：徽记、陪伴感和少量高亮。

同一页面只允许一个语义主强调色；风险状态不得仅靠颜色传达。

## Typography

标题使用书写感中文字体栈，正文使用 Noto Sans SC Variable。标题负责情绪和模块性格，正文负责长时间阅读；不得用极小字号营造“高级感”。正文通常不低于 14px，长段控制在约 65–75 个汉字视觉宽度内。

## Layout

桌面端使用 64px 可悬停展开至 224px 的固定左导航；内容区按模块选择单工作台、主区加右工具轨或沉浸式三栏。页面最大宽度约 1440px。820px 以下切为顶部菜单，右工具轨顺序下沉；520px 以下减少装饰、改为单列，并把桌宠缩至不遮挡主要内容的尺寸。

## Elevation & Depth

深度以纸张层级和柔和环境阴影表达。普通内容不用边框与阴影叠加；悬浮导航、对话窗和粘性工具轨可以使用阴影，表单内部优先靠留白和浅色分区。

## Shapes

控件以 9–12px 圆角为主，普通内容面约 15–18px，模块主视觉可到 26px。胶囊只用于小型状态和筛选，不把所有按钮做成药丸。模块主视觉可使用一个不对称角，形成纸张或书页的识别点。

## Components

- **左侧导航：** 默认窄书脊，悬停展开；激活项使用暖黄色纸签，移动端改抽屉。
- **主要按钮：** 高对比实色，文案直接说明动作；必须包含 hover、focus、disabled 与错误恢复。
- **输入框：** 纸白背景、清晰标签、可见焦点环；占位符不代替标签。
- **右工具轨：** 只收纳当前模块的辅助动作，不重复主页面内容；窄屏下自然下沉。
- **全身引导员：** 桌面端可拖动并记住位置，空闲动作表达陪伴；打开对话后降低角色视觉权重，移动端缩小避免压住任务。
- **信息条目：** 竞赛和通知必须显示来源；演示内容明确标注，不伪装成学校实时通知。

## Do's and Don'ts

### Do

- **Do** 先呈现学生要完成的任务，再暴露 Agent 或 Skill 名称。
- **Do** 让暖心、学习、双创、宿舍和文档页面拥有各自的空间语言。
- **Do** 为音乐、语音、麦克风、AI 请求和记忆提供停止或恢复入口。
- **Do** 使用 Phosphor 同一图标家族，并保持键盘焦点可见。

### Don't

- **Don't** 用“图标 + 标题 + 两行字”的同尺寸卡片铺满所有页面。
- **Don't** 使用紫色渐变、玻璃拟态和无意义科技光效制造 AI 感。
- **Don't** 编造实时学校通知、竞赛名次、用户数据或已接入系统。
- **Don't** 让桌宠、音乐播放器或右侧工具抢走主任务的操作空间。
