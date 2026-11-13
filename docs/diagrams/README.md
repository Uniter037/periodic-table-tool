# 架构交接说明图

对应 v1.8.0 实现基线，2026-11-12 整理。PNG 为 1440×900 预览，SVG 保留可编辑文本和矢量形状。

| 内容 | 图片 | 可编辑版 |
|---|---|---|
| 系统架构与模块关系 | [PNG](01-architecture.png) | [SVG](01-architecture.svg) |
| 输入、校验、绘图、导出 | [PNG](02-data-flow.png) | [SVG](02-data-flow.svg) |
| Agent 调用与版本冲突 | [PNG](03-agent-workflow.png) | [SVG](03-agent-workflow.svg) |
| 样板颜色条与复现验收 | [PNG](04-reference-check.png) | [SVG](04-reference-check.svg) |

从仓库根目录运行 `python docs/diagrams/generate.py` 可重新生成，依赖项目运行环境及中文字体。修改布局或说明后应重新查看四张 PNG，检查文字与连线；SVG 使用系统字体，跨机器显示可能有字体差异。

图 1 为职责概览，完整调用和状态边界以 [架构文档](../ARCHITECTURE-HANDOFF.md) 为准。图 4 的横向颜色条仅用于讲解，原样板为竖直布局。
