# 03. macOS ARM64 原生思考槽位合流架构（v2）与原仓库（v1 `main`）深度对比

本文档记录 `feat/macos-arm64-native-thought-fusion` 分支针对 **macOS Apple Silicon (`arm64` Mach-O, `agy v1.5.4`)** 的逆向工程成果，并详细说明本分支相较于原仓库 `main` 分支（Linux `x86_64`, `agy v1.5.0`）在底层架构与交互体验上的本质演进。

---

## 一、 与原仓库 `main` 分支（v1）的核心差异对照表

| 对比维度 | 原仓库 `main` 分支（v1 方案） | 本分支 `feat/macos-arm64-native-thought-fusion`（v2 方案） |
| :--- | :--- | :--- |
| **目标平台与版本** | 仅支持 **Linux `x86_64` ELF (`agy v1.5.0`)** | 原生支持 **macOS Apple Silicon `arm64` Mach-O (`agy v1.5.4`)**，并自动向下兼容 Linux `x86_64` (`v1.5.0`) |
| **`▸ Thought` 英文摘要根治方式** | **提示词妥协法**：要求模型将内部 `<thought>` 压缩为“2~3 句不换行单段中文 + `【摘要指令】`”，试图哄骗云端 Thought Summarizer 不翻译成英文 | **客户端原生槽位合流（Native Thought Slot Fusion）**：直接修改 `render.stepContent` 机器码，将主模型生成的自然中文思考浓缩直接挂载进 `▸ Thought for Xs, Y tokens` 槽位，100% 覆盖云端英文摘要 |
| **对模型真实推理智力的影响** | **有损**：限制 `<thought>` 只能写 2~3 句且禁写英文/代码，会显著压缩模型在复杂调试与逆向任务中的推演深度 | **零损（100% 满血推理）**：内部 `<thought>` 完全放开，可自由进行上千 token 的多步推演与代码验算；仅将 1~2 句浓缩结果注入 UI 思考槽位 |
| **界面层级与视觉干净度** | **双层分离**：上方保留 `▸ Thought`，下方工具组之间再额外渲染一层白字正文（“我将先…接下来我将…”），存在视觉重复 | **单层原生合一**：中文思考直接以原生浅灰 2 空格缩进渲染在 `▸ Thought for Xs, Y tokens` 正下方，并通过 `bic x8, x8, x8, asr #63` 自动抑制下方重复的白字正文 |
| **流式阶段稳定性** | 伴随正文直接在下方白字区流式吐出 | **首字直入思考槽 + 杜绝“先吐后吞”**：流式阶段（`step.Status != 3 DONE`）与工具调用态（`ToolCalls.len > 0`）全程锚定在 `▸ Thought` 槽位内，配合 `0x02c78fe8` 的 `cmp x2, #0; b.le` 修复，彻底消除流式吐字后消失的闪烁 |
| **思考截断解除（Anti-Truncation）** | `main` 实际生效的 `patch_agy.py` 仅含 1 处 Glamour 4 列右边距补丁，`▸ Thought` 仍会被 `fitDetailText` 单行 `...` 截断 | 完整修补 `collapsedThinkingSnippet`（`0x02c7558c`、`0x02c755d4`）与 `semanticMilestoneLines`（`0x02c64c80`、`0x02c64e58`），彻底废除 `...` 腰斩，按终端宽度自动折行 |
| **提示词文风体验** | 偏向“我将先查看 X，接下来更新 Y”的第一人称动作预告 | **触发必达与表达自然解耦**：强制工具调用步 100% 非空（含几百步历史恢复会话），但拒绝固定三段式模板与机械报幕，像原生 Thought Summarizer 一样自然洗练 |
| **全局规则路径与系统签名** | 仅覆盖 `~/.gemini/GEMINI.md`，无 macOS 代码签名处理 | 同步挂载 `agy v1.5.4` 新版官方全局配置目录 `~/.gemini/config/GEMINI.md` 与 `~/.gemini/GEMINI.md`，并在 macOS 上自动执行 `codesign -f -s -` 防止 `SIGKILL` |

---

## 二、 macOS ARM64 (`agy v1.5.4`) 十处核心二进制补丁详解

在 `agy v1.5.4`（Go 静态编译 Mach-O `arm64`）中，`__TEXT` 段虚拟基址为 `0x100000000`，因此 `FileOffset = VA - 0x100000000`。

### 1. 原生思考槽位中文合流与流式锚定 (`0x02c78624`, 100B)
位于 `render.stepContent` 提取 `CortexStepPlannerResponse` 文本入口：
- 当 `Response` 长度处于 `(0, 640]` 字节区间，且满足 **`ToolCalls.len > 0`（工具调用步）** 或 **`step.Status != 3`（流式生成尚未 `DONE`）** 时：
  - 将 `(x9, x10)`（思考文本指针与长度）直接指向 `Response`（主模型输出的中文思考浓缩）；
  - 将 `x8` 置为 `-1`（`0xffffffffffffffff`，存入栈帧 `[x27, #0x5010]`），作为“已合流思考槽位”的专用负值标记。
- 当步骤无工具调用且已 `DONE`（最终面向用户的正式回答）或长度超过 `640` 字节时，自动走原版逻辑渲染完整 Markdown 正文。

### 2. 折叠思考槽位负值标记跳转修复 (`0x02c78fe8`, 12B) 与低详细度保护 (`0x02c78b18`, 4B)
原版 `render.stepContent` 在 `0x102c78fec` 读取 `x2 = [x27, #0x5010]` 后，使用 `cbz x2, 0x102c79050` 判断是否调用 `collapsedThinkingSnippet` 渲染 `▸ Thought` 下方的第二行摘要——只有 `x2 == 0` 才渲染第二行，若 `x2 = -1` 则会跳过第二行导致中文思考“被吞没”。
- **`0x02c78fe8` (12B)**：合并前序冗余的 `add x27, sp, #0x8, lsl #12`，改写为：
  ```arm64
  ldr  x2, [x27, #0x5010]
  cmp  x2, #0
  b.le 0x102c79050
  ```
  使 `x2 == 0`（原生无正文步）与 `x2 == -1`（中文合流步）均稳定进入 `0x102c79050` 渲染第二行中文思考；而对 `x2 > 0`（最终正式回答步）仍保持单行折叠头，不暴露云端英文摘要。
- **`0x02c78b18` (4B)**：将 `verbosity == "low"` 分支中的 `cbz x8, 0x102c78b38` 改为 `b 0x102c78b38`，确保低详细度下已合流思考块同样正常显示。

### 3. 下方正文重复渲染抑制 (`0x02c78a94`, 8B & `0x02c79b70`, 8B)
在流式与完成态进入 `renderPlannerBody` 前，将 `ldr x8, [x27, #0x5010]` 后的冗余栈基址重算替换为算术右移位清除指令：
```arm64
ldr x8, [x27, #0x5010]
bic x8, x8, x8, asr #63
```
- 当 `x8 == -1`（已合流至上方 `▸ Thought` 槽位）时，`x8 asr #63` 为全 `1`，`bic` 将 `x8` 置 `0`，从而自然跳过下方重复的白字正文渲染；
- 当 `x8 > 0`（最终正式回答步）时，`x8 asr #63` 为 `0`，`x8` 原样保留，正常渲染完整 Markdown 回复。

### 4. 思考摘要全段保留与反省略号截断 (`0x02c7558c`, `0x02c755d4`, `0x02c64c80`, `0x02c64e58`)
- `0x02c7558c` (4B)：绕过 `collapsedThinkingSnippet` 对 `\n\n` 前序段落的裁剪；
- `0x02c755d4` (4B)：将 `collapsedThinkingSnippet` 末尾的 `bl fitDetailText` 替换为 `nop`，废除单行 `...` 腰斩，交由外层 `fitWidth` 按终端宽度自适应软折行；
- `0x02c64c80` & `0x02c64e58` (各 4B)：同步将 `semanticMilestoneLines`（`○ Thought for Xs (...)`）中的两处 `bl fitDetailText` 替换为 `nop`。

### 5. Glamour Markdown 安全折行右边距 (`0x02bb0560`, 32B)
在 `glamour.WithWordWrap.func1` 中利用函数尾部对齐填充区植入 `if width > 20 { width -= 4 }`，彻底消除中文全角标点、弯引号与引用块在终端最右侧的折行吞字问题。

---

## 三、 Linux `x86_64` (`agy v1.5.9`) 十处核心二进制补丁对照与多模型兼容

在 Linux `x86_64` ELF (`agy v1.5.9`) 中，`.rodata` 与 `.text` 均保持 `VirtAddr == FileOffset`（`.text` 基址 `0x06fed000`，Go `gopclntab` 函数表 `textStart = 0x06fed080`）。10 处核心补丁位点与 macOS ARM64 架构 1:1 严格同构：

| 序号 | 文件偏移 (`VA == Offset`) | 大小 | 所属函数 | 机器码改造说明 |
| :---: | :--- | :---: | :--- | :--- |
| 1 | `0x0a455f00` | 23B | `glamour.WithWordWrap.func1` | 当折行宽度 `%rcx > 20` 时执行 `sub $0x4, %rcx`，消除中文引用块右侧边缘吞字 |
| 2 | `0x0a54be00` | 101B | `render.stepContent` | 当 `0 < Response.len <= 640` 且满足 `ToolCalls.len > 0` 或 `step.Status != 3` 时，将 `(%r11, %r12)` 指向中文 `Response` 并置 `%r10 = -1` |
| 3 | `0x0a54cac7` | 2B | `render.stepContent` | 将 `je 0xa54cb25` (`74 5c`) 升级为 `jle` (`7e 5c`)，确保 `%r10 == -1` 合流态进入 `collapsedThinkingSnippet` 渲染浅灰第二行摘要 |
| 4 | `0x0a54c4ee` | 2B | `render.stepContent` | 将 `verbosity == "low"` 分支的 `je 0xa54c50e` (`74 1e`) 升级为 `jle` (`7e 1e`)，防止低详细度跳过已合流思考块 |
| 5 | `0x0a54cd05` | 6B | `render.stepContent` | 在流式与完成态总汇聚闸门将 `je 0xa54cf58` (`0f 84`) 升级为 `jle` (`0f 8e`)，自动跳过下方 `renderPlannerBody` 重复白字渲染 |
| 6 | `0x0a5483dc` | 2B | `render.collapsedThinkingSnippet` | 将 `jl 0xa548410` (`7c 32`) 改为 `jmp` (`eb 32`)，禁止裁剪 `\n\n` 前序段落 |
| 7 | `0x0a54842a` | 5B | `render.collapsedThinkingSnippet` | 将 `callq fitDetailText` 替换为 5B `nop`，废除折叠槽单行 `...` 腰斩 |
| 8 | `0x0a54c2cf` | 5B | `render.stepContent` | 将流式纯思考分支的 `callq fitDetailText` 替换为 5B `nop`，流式阶段同样完整折行 |
| 9 | `0x0a5345b8` | 5B | `render.semanticMilestoneLines` | 移除 `○ Thought for Xs (...)` 分支 1 的 `fitDetailText` 单行截断 |
| 10 | `0x0a5347d9` | 5B | `render.semanticMilestoneLines` | 移除 `○ Thought for Xs (...)` 分支 2 的 `fitDetailText` 单行截断 |

### Claude 模型兼容实测结论
经核验 `Claude Opus 4.6` 与 `Claude Opus 5.5` 真实会话日志：Anthropic API 默认开启服务端 Summarized Thinking（常将思考摘要重写为英文），且在连续工具调用轮次常返回空 `thinking=""`、仅在 `content` 输出中文说明。v2 合流补丁将中文伴随文本直接注入 `(%r11, %r12)` 思考槽位并抑制重复正文后，Claude 与 Gemini 均可获得 100% 原生一致的浅灰中文思考槽位体验，无需按模型单独分支处理。

---

## 四、 性能与延迟评估

- **零额外网络往返**：无本地代理转发或二次翻译请求。
- **极低 Token 开销**：每步仅生成约 25~55 个中文 Token（耗时约 `0.15s ~ 0.35s`），相比动辄 5s~30s 的内部推理与工具执行开销几乎零感知，且因无需在下方额外输出冗长过渡段，整体交互更加紧凑利落。
