# Agent 高效绘图流程

本页描述 v1.9.0 的 Agent 与排版增强，API 仍为 v1。源码与 v1.9.0 EXE 均支持这些功能；已下载的旧版 EXE 需要更新。使用前先调用 `describe` 检查返回 actions。

## 1. 一次请求直接成图

一次性绘图使用 `render`，无需先创建项目、查询 revision 或保存修改。它以默认自定义样式为基础应用 patch，沿用同一科学参数校验和绘图内核，输出自动命名图片。

```powershell
python -m application.agent_api --request examples/agent/render.json --response output/render-result.json
```

示例输出 PNG/SVG/PDF。所有数据、配色、数值格式、隐藏元素、颜色条、画幅和字体设置都通过 patch 提供，格式与 create/update 相同。render 不持久化项目；需要继续编辑时使用 create/update/export 流程。

## 2. 批量导出已有 Excel 数据组

`batch_export` 从项目保存的 Excel 数据集合中选择组，共用当前图形配置和色标，最多 100 组。只能选择同一个指标的组，避免将不同量纲混为一张可比较系列。

```json
{
  "api_version": 1,
  "action": "batch_export",
  "project": "output/my-project.ptproj",
  "expected_revision": "用 inspect 返回的 revision 替换",
  "dataset_ids": ["用项目中的真实 dataset ID 替换"],
  "output_dir": "output/batch",
  "formats": ["png", "svg"]
}
```

省略 dataset_ids 选择全部组；显式选择的顺序决定输出顺序。重复或未知 ID 应被拒绝。项目中的当前编辑和各组 manual_data 优先于来源快照，批量导出不改变项目、当前选中组或原工作簿。

各组共用既定范围，不自动为每张图重新缩放。出现超范围警告时先检查数值与色标，确实接受截断时才设置 allow_out_of_range=true。批量失败会清理本轮创建的图片，不删除原有文件；这是进程可处理异常时的清理，不是断电后的跨文件事务恢复。

## 3. 让模型正确填写参数

优先使用 describe 返回的 parameter_options，按参数名读取可接受值数组。原 parameter_choices 保留以兼容旧客户端；它可能是中文显示值到内部值的映射，不应假定全部为数组。

`action_required_fields` 列出各 action 的核心必填字段；公共 api_version/action 仍必填，部分字段存在条件要求（例如导入需要选定 sheet、render 需要非空数据）。`action_metadata` 描述新增操作的无状态特性、批量限制和返回字段。

render 成功返回 warnings/layout_issues/files；batch_export 同时返回 project/revision/dataset_ids、按组的 datasets（dataset_id/name/warnings/layout_issues/files）以及展平后的 files。所有文件项均含 path/bytes/sha256。建议按 dataset_id 建立结果对应关系，不依赖文件名解析业务 ID。

params 中的数值通常仍采用字符串，如 dpi="150"；data 则采用数值或原始文本。新元数据不会改变项目字段类型。不要把内部 fmt="4f" 直接写入需要中文选项的 params，使用 describe 列出的接受值。

## 4. 冲突恢复

REVISION_CONFLICT 的 details 提供 expected_revision、current_revision 和恢复提示。current_revision 用于诊断，不是无条件覆盖授权：重新 inspect，比较 document，重新 validate 原 patch 或调整 patch 后再提交。

接口保留旧 action 和 API_VERSION=1。客户端应容忍成功响应新增字段，但发送请求时只使用 describe 声明的字段。始终检查进程退出码、响应文件与 ok，而不是仅检查图片目录存在。

## 5. 接口调用选择

| 任务 | 推荐调用 |
|---|---|
| 一次性合成图、参数试绘 | describe → render |
| 可继续编辑的新项目 | create → export |
| 修改既有项目 | inspect → validate → update → export |
| 同一指标多组对比 | inspect → batch_export |
| 导入 Excel 后保留全部数据组 | excel_preview → import_excel → inspect → batch_export |

图片与参考样板是否一致仍需视觉验收。共享色标、真实数据、隐藏元素、舍入规则和物理画幅都必须匹配，不能只替换颜色条标签。

## 6. 排版诊断与颜色条占位

`render`、`export` 成功结果包含 `layout_issues`，`batch_export` 在每个 `datasets` 项内返回对应数据组的 `layout_issues`，请按 dataset_id 关联问题。默认 `display.check_label_overlap=true`，同时将排版提示汇总到 warnings。`TEXT_OVERLAP` 包含 text、other 和 suggestion；`TEXT_OUTSIDE_CELL` 包含 text 和 suggestion。每个文字描述包含 element、role 和 bounds；bounds 为 Figure fraction 的 `[x, y, width, height]`，原点位于画布左下角。

诊断基于渲染后的文字包围盒，并非逐字形的精确相交判定，因此仅供人工排版参考，不会自动移动标注或修改数据。单纯的排版提示不会触发 RANGE_WARNING，也不需要 allow_out_of_range 确认；真实的数值超范围仍沿用原确认流程。设置 `display.check_label_overlap=false` 可关闭诊断，返回空 layout_issues。`validate` 只校验配置，不渲染图片，不能代替导出后的排版检查。

需要在显示和隐藏颜色条之间保持主图坐标轴位置稳定时，设置 `display.preserve_cbar_space=true`，再用 show_cbar 控制颜色条显示。此选项默认为 false。单元素的 element_overrides.value_dx/value_dy 与全局偏移相加，可据诊断提示调整对应数值标注；导出后仍应进行视觉验收。

对照图建议同时设置 `params.crop_mode="固定画幅"`。紧裁切会随可见内容改变最终图片边界，即使 Figure 内的主图坐标保持一致，输出文件的尺寸和留白仍可能不同。检测目前针对元素单元格文字，不包含颜色条刻度或标题之间的碰撞。
