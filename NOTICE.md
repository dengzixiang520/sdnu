# 第三方素材署名与许可

本项目自身代码为原创。以下第三方素材按各自许可证使用，均用于**非商业**的竞赛演示场景。

---

## 暖心引导员「小曦瑶」角色动画

- **素材**：dsh-pet 桌宠「大肥鱼」动画包（`default` 包，原 106 段动画）
- **作者**：PC2005-cloud
- **许可证**：CC BY-NC-SA 4.0（署名 + 非商业性使用 + 相同方式共享）
  <https://creativecommons.org/licenses/by-nc-sa/4.0/>
- **本项目使用方式**：选取 13 段与「暖心引导员」角色定位相符的动画（待机、点击回应、
  思考、说话、被拖拽、吃零食等），裁切角色区域、缩放至 160×172、将纯黑背景抠成
  透明通道，转码为动画 WebP 存于 `web/public/pet/`。
- **修改说明**：原素材为 640×360、VP9 编码、纯黑背景；本项目做了裁剪、缩放、
  透明化与格式转换，属于 CC BY-NC-SA 4.0 允许的「演绎」行为。演绎后的动画文件
  同样以 CC BY-NC-SA 4.0 提供。
- **未使用部分**：原包其余 93 段动画未纳入本项目。

角色「大肥鱼」形象设计基于 ZipZipPipe 与 上善无形（B 站）。

---

## 桌宠交互设计参考

- **参考对象**：dsh-pet / kiriyuki.com 桌面宠物
- **借鉴内容**：甩出后抛物线飞行 + 边界反弹 + 落地挤压的物理参数思路
  （`gravity 1400` / `restitution 0.78` / `groundFriction 2.5`），以及
  「指针移动驱动角色朝向」的交互模式。
- **实现方式**：本项目为独立实现，未复制其源代码；物理与注视逻辑见
  `web/src/components/GuidePet.vue`。
- **未使用**：kiriyuki.com 的 Live2D 模型与运行时（未随本项目分发）。

「能量卡」为本项目自行设计，展示本平台自身数据（打卡、积分、等级、分享墙），
与原桌宠的 DeepSeek 账户余额卡片无关。

---

## 其他

- 图标：`@phosphor-icons/vue`（MIT）
- 字体：`@fontsource-variable/noto-sans-scope`（SIL OFL 1.1）、`LXGW WenKai`（SIL OFL 1.1）
- 大模型：DeepSeek API（`deepseek-chat`），通过 `zhihui_qilu.ai.provider` 适配层调用

---

如对上述署名或许可有疑问，请通过参赛材料中的联系方式与作者沟通。
