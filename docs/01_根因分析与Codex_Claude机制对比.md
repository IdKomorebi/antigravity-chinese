# 01. Antigravity CLI 中文支持痛点根因分析与 Codex / Claude Code 机制深度对比

> **记录时间**：2026-11-04
> **工作目录**：`~/projects/antigravity-chinese`
> **分析对象**：
> 1. Antigravity CLI (`~/.local/bin/agy`，版本 `1.4.12`，Go + BubbleTea 架构)
> 2. OpenAI Codex CLI (`~/.local/bin/codex`，Rust 原生构建 + `gpt-6.1-sol`)
> 3. Anthropic Claude Code (`~/.local/bin/claude`，版本 `2.1.259`，`claude-opus-4-6`)

---

## 一、 用户核心痛点与四大底层根因拆解

通过对本机 `~/.local/bin/agy` 二进制文件的符号表（`.gopclntab`）、只读数据段（`.rodata`）与渲染状态机（`jetski/cli/render`）进行逆向反汇编，并结合历史会话日志（`transcript.jsonl`）对比，定位出四大根本原因：

### 1. 为什么设置了中文规则，`Thought for Xs` 下的思考过程依然常常是英文？
- **云端二级推理摘要器（Thought Summarizer）的语言漂移**：
  Antigravity CLI 调用的 Gemini 3.x / 2.5 模型在云端开启了 `includeThoughts`。其返回给客户端的 `thinking` 字段**并非原始推理流**，而是经过 Google 云端一层轻量级 **Thought Summarizer（推理摘要器）** 二次提炼后的第三人称摘要（特征句式如 `The user wants...`、`The make_entry function in toc.py is central...`、`Need to meticulously check...`）。
- **混合语言触发英文摘要**：
  当主模型在思考中夹杂了英文习惯用语（如 `Let's check`）、大段英文系统提示词复述或直接拼凑代码片段时，云端摘要器会判定当前思维链语境为英文，从而强制将整段思考摘要重写为英文。
- **解决关键**：
  必须在全局规则中显式约束模型**以“中文进度简报”风格组织思考**，严禁在思考开头复述英文 Prompt 或使用英文过渡词，从源头锁定云端摘要器的输出语言为中文。

### 2. 为什么思考过程在终端里总是只显示半行并以 `...` 截断？
- **定位函数**：`jetski/cli/render/render.stepContent`（虚拟地址 `0x9ba2a80`）与 `jetski/cli/render/render.collapsedThinkingSnippet`（虚拟地址 `0x9b9fc00`）。
- **代码逻辑**：
  在 `stepContent` 的 `0x9ba3893` ~ `0x9ba38a2` 处，渲染器检查当前面板的折叠状态 `expanded`：
  - 默认情况下 `expanded == false`（即未按 `Ctrl+O`），程序在 `0x9ba38a2` 处执行 `je 0x9ba39d6`，跳转到 `collapsedThinkingSnippet`。
  - `collapsedThinkingSnippet` 仅提取思考内容的最后一个非空段落，随后调用 `fitDetailText`（`0x9b8b500`）按单行终端宽度硬性截断，并在末尾拼接 `"..."`。
  - 更糟的是，当 AI 连续发起工具调用进入 `CollapsedToolGroup` 时，一旦输出最终回答，前面的思考摘要甚至会被直接折叠隐藏。

### 3. 为什么 `Bash(...)` 工具调用只显示冗长生硬的命令截断，缺少清晰简短的中文目的说明？
- **定位函数**：`jetski/cli/render/render.toolStepInfo`（虚拟地址 `0x9b9ada0`）与 `jetski/cli/render/render.toolSummaryFromMetadata`（虚拟地址 `0x9b9ed80`）。
- **代码逻辑（关键发现）**：
  - 实际上，Antigravity 的 `run_command` 工具 Schema **本来就包含必填的 `toolSummary` 字段**（且模型在遵循中文规则时，已经在该字段中填入如 `"重新生成V6完整版文档与目录"` 的中文简述）。
  - 在 `toolStepInfo` 中，渲染器甚至专门实现了辅助函数 `toolSummaryFromMetadata`（`0x9b9ed80`），用于从 `step.Metadata.ToolCall.Arguments` JSON 中解析 `"toolSummary"`！
  - **但是**，在 `toolStepInfo` 处理 `CortexStepRunCommand`（即 `Bash`）的分支（`0x9b9b77d` ~ `0x9b9b7c0`）中，官方程序员**直接硬编码读取了 `runCommand.CommandLine`（`0x8(%rdx)` / `0x10(%rdx)`）作为括号内的标题**，完全忽略了 `toolSummary`！这导致终端上只能看到 `Bash(python3 "reports/南网/..."...)` 这种半截命令行，而看不到中文目的。

### 4. 为什么最终回答里的中文引用块（`> ...`）会出现竖线错位和右侧边缘吞字？
- **定位函数**：`jetski/cli/render/render.renderPlannerBody`（`0x9b807c0`） -> `renderMarkdownUncached`（`0x9b7a1e0`） -> `glamourRender`（`0x9b7b6e0`）。
- **代码逻辑**：
  - `agy` 使用 Go 的 `charmbracelet/glamour` + `lipgloss` + `go-runewidth` 渲染 Markdown。
  - 当模型使用 `> ...` 引用块包裹长段中文、且段落内包含中文弯引号 `“` `”`（`U+201C` / `U+201D`，属于 Unicode 东亚模糊宽度字符 Ambiguous Width）与英文/数字混排时，`go-runewidth` 计算出的列宽（1 列）与部分终端实际渲染宽度（2 列）产生累积偏差，导致单行实际渲染宽度超出终端视口右边界 1~2 个字符，触发终端强行折行（使下一行开头脱离左侧 `│` 引用线）或被 BubbleTea 视口右侧裁剪吞字。

---

## 二、 深入学习本机 Codex CLI 与 Claude Code 的成熟设计

为了打造媲美甚至超越主流工具的中文体验，我们对本机已安装的 **Codex CLI** 与 **Claude Code** 进行了配置文件、真实历史会话（`.jsonl`）与二进制提示词的深度剖析。

### 1. OpenAI Codex CLI (`~/.codex`) 的核心机制：双通道解说（`commentary` + `final`）

通过对本机会话日志 `~/.codex/sessions/2026/10/31/rollout-2026-10-31T00-07-33-01a18d91-02be-75d2-86d0-59a6c53b7c11.jsonl` 的拆解，我们发现 Codex 之所以在中文环境下条理极其清晰，秘诀在于其 **双通道输出架构**：

1. **隐藏杂乱的底层草稿，暴露精炼的中间解说（`commentary` 通道）**：
   - 在 JSONL 日志中，Codex 的底层 `reasoning` 对象实际上是加密的（`summary: []`），它不会把模型混杂着英文 API 名称、正则试错的原始草稿直接甩给用户。
   - 相反，Codex 在系统提示词中定义了严格的 **`## Intermediate commentary`** 规范：
     - **触发时机**：在开始一系列工具调用前、取得关键阶段性发现时、或连续工作每 30~60 秒时。
     - **风格要求**：1~2 句简短、自然、面向用户的中文进度说明。
   - **本机真实日志范例**（摘自上述会话）：
     - 调用工具前：`"[commentary] 我先检查服务器环境和是否已有安装，再安装官方 Antigravity CLI，并验证能否启动。"`
     - 阶段性发现时：`"[commentary] 查到了：现在有官方 Antigravity VS Code 扩展和 CLI，另外 npm 上那些第三方包不是官方本体。我继续核对 Linux 下官方安装入口和命令名。"`
     - 深入排查时：`"[commentary] 已确认官方包里有远程 CLI 脚本和二进制入口。我现在直接测试这台机器上的 CLI 启动行为，看在无桌面服务器里是直接可用还是需要附加子命令。"`
2. **启发与借鉴**：
   在 Antigravity CLI 中，除了让 `Thought` 本身保持中文外，我们还可以通过规则引导模型在**每组关键工具调用前后输出 1 句精炼的中文阶段进度简报（Commentary）**。这样既解决了连续工具调用没有上下文过渡的问题，又能在界面上形成像 Codex 一样清晰的任务脉络！

### 2. Anthropic Claude Code (`~/.claude`) 的核心机制：三层协同设计

通过对本机 `~/.claude/projects/-data1-duhaocun-projects-GNN-Aggresvation/` 下的记忆文件 `language-chinese.md`、会话日志 `6f0d3f84-5eef-48dc-816f-b76c2367a93b.jsonl` 以及二进制 `~/.local/share/claude/versions/2.1.259` 的分析，总结出 Claude Code 的三大设计亮点：

1. **第一层：极简原生中文笔记式 Thinking**：
   - Claude Code 配合 `language-chinese.md` 后，其 `thinking` 块不写冗长的自我对话，而是采用**“已完成什么 -> 发现了什么 -> 下一步做什么”**的中文简明笔记体。
   - **本机真实日志范例**（摘自 `6f0d3f84-...jsonl`）：
     - `"已看完4月PPT，内容是通过节点电价与安全约束机组组合反向逆推电网拓扑和线路参数。接下来看10月PPT和信息披露细则。"`
     - `"现在我已经完整阅读了两个PPT和信息披露细则。让我梳理一下核心逻辑，给用户一个清晰的总结和方向确认。"`
2. **第二层：每个工具调用自带简短中文意图描述（`description`）**：
   - Claude Code 的 `Bash` 工具 Schema 中包含 `description: "Clear, concise description of what this command does in 5-10 words"`。在终端 UI 上，用户可以一眼看到这个命令的目的，而不是去啃几百字符的 Shell 脚本。
   - 这与我们即将通过二进制补丁解锁 Antigravity CLI 的 `Bash(中文 toolSummary)` 异曲同工！
3. **第三层：静默轮次进度提醒（Silent-Turn Progress Reminder）**：
   - 逆向 Claude Code `2.1.259` 二进制发现，其内置了进度提醒机制：
     `"The user hasn't heard from you in a while — say in a few words what you're doing, then continue."`
   - 当模型连续执行多步工具调用时，强制要求模型每隔几步用一两句话向用户汇报当前阶段结论与下一步动作，最后在任务结束时给出结构化的精炼总结。

---

## 三、 综合改造方案设计（二进制补丁 + 提示词工程双剑合璧）

结合上述根因分析与对 Codex / Claude Code 的学习，我们在 `~/projects/antigravity-chinese` 隔离环境中实施以下四位一体改造：

| 维度 | 改造项 | 实现层级 | 达成效果 |
| :--- | :--- | :--- | :--- |
| **1. 工具调用展示** | 解锁 `Bash` 优先显示 `toolSummary` | **二进制代码补丁** (`0x9b9b78d`) | 将原本冗长截断的 `● Bash(python3 "reports/..."...)` 变为清晰直观的 `● Bash(重新生成V6完整版文档与目录)`，无 `toolSummary` 时自动安全回退显示原命令。 |
| **2. 思考过程展示** | 解除单行 `...` 截断，默认完整多行展示 | **二进制代码补丁** (`0x9ba38a2`) | 绕过 `collapsedThinkingSnippet` 的单行截断，默认完整、多行、带缩进地展示全部思考过程，不再出现半截英文 `...`。 |
| **3. 界面词条汉化 + 渲染防吞字** | 核心 UI 词条汉化 + Markdown 安全列宽边距 | **二进制数据/代码补丁** (`.rodata` & `0x9b809a1`) | 将 `Thought for %s, %s tokens` 汉化为 `思考耗时 %s, %s词元`、`Thought for %s` 汉化为 `已思考 %s`、`Thought Process` 汉化为 `思考与推理`、`ctrl+o to expand` 汉化为 `按ctrl+o展开`；同时为正文渲染预留安全边距，彻底消除右侧吞字。 |
| **4. 思考语言锁定与阶段简报** | 融合 Codex `Commentary` 与 Claude 笔记体思考 | **增强版全局规则** (`rules/GEMINI_ZH_BEST_PRACTICES.md`) | 锁定云端 Thought Summarizer 为 100% 中文笔记体；要求每个 `toolSummary` 必填简短中文动宾短语；连续工具调用间穿插 1~2 句 Codex 风格的中文阶段简报。 |
