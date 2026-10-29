# 作品集展示与前端方案

决策日期：2026-10-28。项目按企业 Agent 脱敏重构作品收敛，展示已有设计，不继续扩建模拟业务与通用平台能力。

## 对外定位

推荐一句话：**从企业安全运营场景抽离的调查 Agent 重构：用显式状态、确定性策略和人工审核约束模型推理。**

介绍顺序：场景中的调查问题 → 原有工程痛点 → 本仓库的设计取舍 → 一条调查路径 → 验证与限制。将企业原系统经验与本仓库成果分开，不把原系统的线上成绩转移到重构版。

个人贡献由作者按事实确认：实习阶段参与什么、继承哪些领域经验、在个人重构阶段实际设计和实现什么。架构图和代码能佐证设计；不能替代作者确认经历和贡献。

## 展示材料的最小集合

| 材料 | 回答的问题 | 当前入口 |
|---|---|---|
| README | 项目做什么、为什么有价值 | [README](../README.md) |
| 系统架构图 | 状态、工具、模型、人工如何分工 | [SVG](architecture.svg)、[PNG](architecture.png) |
| 工作流与模型边界 | 谁决定路由、数值、风险与后续动作 | [设计说明](architecture/agent_runtime_position.md) |
| 当前版本截图 / 短视频 | 一次调查如何产生证据和报告 | [素材手册](自助演示与素材手册.md)；截图与录制尚待更新 |
| 接口与验证说明 | 怎样运行、已验证到什么程度 | [REFERENCE](REFERENCE.md) |

现有 `gap-analysis-assets/` 截图、`showcase_readiness.html`、`portfolio-gap-analysis.html` 属于历史评审材料，不代表当前界面或能力。当前不包含无需模型的录制回放播放器，不能把它写成已交付功能。

## 前端是否值得再做一次

值得进行一次有限的展示整理：提高阅读效率，让评审看清证据、边界和产出。当前 React 19 + Vite + Tailwind v4 + shadcn/ui 可以承载这个目标；框架替换不直接带来视觉和信息层次的改进。

建议页面结构：

1. **调查概览**：目标、当前阶段、分项风险和数据覆盖说明；不堆叠无关 KPI。
2. **过程与证据**：阶段列表、资产分组、工具摘要；原始参数与结果放入详情区。
3. **审核状态**：说明当前是在审核继续生成报告，按钮表达实际动作。
4. **结论与报告**：突出发现、根因假设、证据和处置建议之间的关系。

UI 文案应说“执行过程/调查记录”，不把模型私有思维链当作可展示内容。当前没有可靠数据的时间、费用、置信度不应填充假数值。改造预算以一次有限收尾为准，优先控制台排版、密度、字号、留白和状态；不增加图编辑器、完整聊天系统或用户中心。

## 开源方案比较

以下能力依据项目官方仓库/文档核对；成本是结合本仓库自定义 POST SSE 与状态结构作出的判断，不是完成接入后的测量。

| 方案 | 能借用的能力 | 本项目接入判断 |
|---|---|---|
| [shadcn/ui Blocks](https://ui.shadcn.com/blocks) / [源码](https://github.com/shadcn-ui/ui) | 可复制修改的 dashboard、sidebar 和布局组件 | **首选**：沿用现有栈，借用版式与组件，保留本项目调查数据和 SSE |
| [LangChain Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui) / [官方说明](https://docs.langchain.com/oss/python/langgraph/ui) | 工具调用、中断、会话与报告侧栏等交互参考 | 适合聊天形态；默认面向 LangGraph server 与 messages。本项目是自定义 FastAPI 接口，不能仅替换 URL，需适配服务或前端数据层 |
| [assistant-ui](https://github.com/assistant-ui/assistant-ui) / [ExternalStoreRuntime](https://www.assistant-ui.com/docs/runtimes/custom/external-store) | React 对话 primitives、自定义工具展示、自带状态接入方式 | 可局部借用；现有状态可通过自定义适配接入，但仍需设计调查布局，完整迁移收益有限 |
| [CopilotKit](https://github.com/CopilotKit/CopilotKit) | Generative UI、共享状态、人工交互 | 能承载这类交互，但引入协议/运行时适配。现有 `agui.ts` 不是已实现的兼容桥，不宜作为本次收尾首选 |
| [React Flow](https://github.com/xyflow/xyflow) | 节点图与流程可视化 | 若未来确需交互执行图再考虑；当前静态 SVG 与 Mermaid 已能解释架构，无需增加运行依赖 |

现阶段选择：**保持专门的调查工作台，用成熟开源组件和版式完成视觉收尾。** 不为了 Agent 标签把界面改成通用聊天框。若之后明确改为对话产品，再重新评估 Agent Chat UI / assistant-ui。

## 完结标准

可以在不了解原企业环境的前提下解释项目；架构和能力声明能由代码对应；展示图像匹配当前版本；已有验证范围和限制写清。提供可运行演示时，先修复影响演示路径的既有缺陷并人工验证。具体清单见 [todo.md](../todo.md)。

real 模式联调、扩充事故评估、本地企业环境模拟、MCP、OTel 和多租户不再作为本项目完结条件。
