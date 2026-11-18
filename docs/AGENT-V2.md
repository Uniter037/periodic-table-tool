# 独立绘图引擎与 Agent v2（源码开发版）

本接口使用独立 PlotSpec，不读取原脚本样式注册表，不需要 `mode_id` 或 `compatibility`。源码默认桌面已接入同一内核，可编辑 schema 2 项目；已发行 v1.9.0 EXE 仍使用旧项目入口。schema 2 项目不能由旧桌面打开。API v1 暂时保留，支持迁移期已有调用。

## 调用

沿用现有入口，将请求的 `api_version` 设置为 `2`：

```powershell
python main.py --agent-request examples/agent-v2-render.json --agent-response output/v2-result.json
```

示例使用合成数据，生成 PNG 与 SVG；文件自动加时间戳和冲突序号。请求可以通过 `python -m application.agent_api --request ...` 调用。不要用旧 EXE 发送 v2 请求；它尚未包含新内核。

先发送 `{"api_version":2,"action":"describe"}` 查询默认配置、普通预设和动作字段。绘图配置字段见 [PlotSpec 契约](PLOT-SPEC-V2.md)。中文标签只用于显示，接口枚举保持稳定。

## 项目编辑

创建：`{"api_version":2,"action":"create","project":"output/sample-v2.ptproj","preset":"diverging","data":{"Ni":0.5,"Ti":-0.5}}`。

读取：`{"api_version":2,"action":"inspect","project":"output/sample-v2.ptproj"}`。响应包含 `revision`、完整文档和规范化的 `resolved_plot`。

修改：使用最新 revision 作为 `expected_revision`，调用 `update`，例如：

```json
{
  "api_version": 2,
  "action": "update",
  "project": "output/sample-v2.ptproj",
  "expected_revision": "从 inspect 取得的 revision",
  "patch": {
    "plot": {"value_fs": 9, "show_cbar": false},
    "data": {"Ni": 0.75, "Ti": null}
  }
}
```

`plot` 按顶层字段合并；`cbar`、`element_overrides` 等嵌套值整体替换，提交前从 inspect 读取原值再修改。`data` 合并，null 删除元素；`replace_data=true` 先清空再合并。任何改动失败不写项目。`validate` 使用同样 patch 进行只读验证，不产生新 revision。

导出用 `export`，提供 project、output_dir、formats、base；可提供 expected_revision 检查版本。超出范围或折叠布局隐藏输入元素会提示，确认这些行为符合需求时显式传 `allow_out_of_range=true`。渲染返回图元诊断 `layout_issues` 和 `plot_fingerprint`；相同规范化配置与数据可用该指纹比较。

## Excel 与批量

`excel_preview`、`import_excel` 延用原区域映射参数；`import_excel` 需要 expected_revision。导入后返回 dataset_ids，`update` 可指定 dataset_id 切换组，当前手动编辑保留在所属组。

`batch_export` 接受 dataset_ids，最多100组且必须属于同一指标。所有组使用当前 PlotSpec 的固定色标，先验证全部数据再输出；失败清理本轮已创建文件，不删除此前结果。批量文件按请求顺序编号，响应保留组名与 ID。

## 迁移旧项目

先发送 `{"api_version":2,"action":"migrate","project":"old.ptproj"}`。默认 `dry_run=true`，不写任何文件，返回转换结果、差异报告及 source_revision。

复核报告后发送同样请求并加入 `dry_run=false`、`expected_revision=source_revision`；默认另存为 `old-migrated.ptproj`，可用 output_project 指定新路径。禁止覆盖源项目或已有目标。旧数据和状态均保留，历史模式名只作为来源信息，不影响新渲染。

有色图预览器状态等无法转换的语义时返回 `MIGRATION_BLOCKED` 和结构化差异报告；不要通过删除字段绕过报错。需要历史逐像素复现时继续使用旧发行版，新的科学规则会明确区分零值与缺失并正确标注镧锕范围。

## 边界

- 这是本地文件接口，不开端口，不接受代码、模块路径或表达式。
- GUI 与其他外部编辑器不参与 API 文件锁；外部修改前关闭项目，修改后重新加载。revision 不等于跨应用事务锁。
- 返回的预设是普通配置快照，应用后每个适用字段都可修改；不继续按旧脚本身份限制选项。
- 本轮不新增其他绘图库，不更改实验原始数据，不自动“纠正”用户显式指定的范围。
