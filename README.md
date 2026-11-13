# 元素周期表绘图工作台

当前版本：v1.9.0。

v1.9.0 新增 Agent 能力：[一次请求绘图、Excel 数据组批量导出及调用优化](docs/AGENT-WORKFLOWS.md)。源码与 v1.9.0 EXE 均支持这些功能；调用前用 `describe` 查询能力，旧版 EXE 需更新。

v1.9.0 新增排版辅助：在图形设置中可开关“检查标注重叠”（默认开启），预览底部提示可能重叠或越界的元素，保留手动字号和位置。颜色条设置新增“隐藏颜色条时保持主图位置和大小”（默认关闭）；配合“固定画幅”使用，便于生成位置一致的对照图。Agent 导出响应包含 `layout_issues`，详见上述调用文档。

开发与交接：[当前版本架构、模块职责、数据契约和扩展指南](docs/ARCHITECTURE-HANDOFF.md) · [环境、日志排错、测试与发行操作](docs/HANDOFF-OPERATIONS.md)。交接文档区分当前实现与后续规划，新接手的开发者或 Agent 建议从这里开始。

## v1.9.0 新增

- Agent `render` 一次请求直接成图，无需持久化项目；`batch_export` 对项目内同一指标的 Excel 数据组共用色标导出，最多 100 组。
- `describe` 新增 `parameter_options`、`action_required_fields` 和 `action_metadata`；`REVISION_CONFLICT` 提供预期/当前 revision 与恢复提示，冲突后仍须重新检查项目。
- 标注重叠/越界诊断默认开启（`display.check_label_overlap=true`），Agent 导出返回 `layout_issues`；提示不会自动移动文字或改变数据。
- 隐藏颜色条时保留主图位置和大小为可选项（`display.preserve_cbar_space=false`，默认关闭）；对照图请配合固定画幅。

## v1.8.0 已有功能

- 科学模式修正锕系范围为 89～103，默认采用十进制四舍五入；可选原脚本浮点舍入，原脚本兼容样式保留历史输出。
- 单元素显示、着色、参与自动范围分别设置，隐藏保留原值；标注和颜色条可拖动，支持撤销与项目保存。
- 预设默认只保存和套用样式，保留当前 Excel 数据组；需要替换数据时显式勾选「包含数据」。
- PNG/JPG/SVG 样图对照窗口，独立缩放和平移，手动刷新当前预览快照。
- 毫米画幅、精确主图区边距与颜色条位置尺寸，固定画幅或紧裁切可选。
- 直接导入 `.xlsx`：选择工作表、元素/条件/数值区域，支持横向和纵向矩阵；读取已保存的公式结果，不执行公式。
- 导入后保留全部数据组，通过「项目 → 切换 Excel 数据组」切换，各组编辑和当前选择随项目保存。
- 「日志与排错」提供即时开关、级别、临时详细排错和本次诊断包导出。

当前Excel导入为矩阵模式；分类分组导入、自动源更新仍在后续迭代中。已导入的同一指标可在「项目 → 批量导出已导入数据组」中选择多组共用当前色标导出。项目内保存数据快照，原Excel不被修改。新增项目字段建议使用本版继续编辑，旧版不会保留这些扩展信息。


开发设计：[Excel 绘图工作台产品规格、模块化架构与子代理任务书](docs/workbench/README.md)。这是后续迭代设计，当前版本的已实现功能以本文使用说明为准。

把元素数值或文本标注制作成可用于报告、论文和演示的周期表图片。日常绘图使用修正后的绘图配置；需要复现历史结果时，开启原脚本兼容选项。

## 启动

Windows 免环境版：打开发行包中的 `PeriodicTableTool.exe`。源码版：

```bash
python -m pip install -r requirements.txt
python main.py
```

运行依赖 Python 3.10+、Tkinter、Matplotlib、NumPy、Pillow 和 resvg_py。元素数据已内置，无需 mendeleev。源码构建与 EXE 构建方法见文末。

## 完成第一张图

1. 选择「自定义热力图」。
2. 点击「载入示例」体验，或导入 `examples/heatmap.txt`、粘贴两列元素数据。
3. 用「自动范围」让颜色范围适配当前数据；需要比较多张图时，手动固定最小、中心和最大值。
4. 调整色图、字号、数值格式、颜色条标注，检查右侧预览。
5. 设置输出格式、尺寸和分辨率，然后点击「导出图片」。

导出文件自动添加时间戳及必要序号，不覆盖已有图片。SVG/PDF 适合缩放和排版，PNG 适合直接插入文档。

预览和导出在独立绘图进程中执行，底部显示任务进度；点击「取消任务」可停止当前任务。连续修改参数时只采用最后一次请求的结果。首次启动绘图进程可能稍慢，随后会复用进程；预览分辨率有上限，正式导出仍使用指定的画幅与 DPI。

「项目 → 批量导出（共用当前色标）」可选择多个数据文件。先设置统一的最小、中心、最大值及输出格式，再执行批量导出；超出范围时会提示确认。批量结果在本轮全部渲染完成后写入输出目录，取消时未发布的临时结果会清理。

## 工作区与操作

顶部操作栏提供数据导入、粘贴、示例和导出入口。设置按图形、配色/颜色条、预设/输出分组，内容可滚动。预览按固定画幅等比显示，窗口大小不会改变自定义图片的构图。

双击数据表中的数值即可编辑。数据表和图形化标注共用同一份数据。修正绘图将 `0` 视为有效值，未填写的元素才视为空值。导入保留原始文本，因此标注图中的 `001`、`1.00`、`1e3` 不会因数值转换丢失格式。

预览支持滚轮缩放、右键拖动；通过「视图 → 预览适合窗口」恢复全图。窗口和预览缩放不会改变导出尺寸。自动布局根据可用空间调整，也可在「视图」菜单固定布局、界面缩放和预览区比例。

### 在预览中编辑元素标注

「图形标注：点击编辑 / 左拖移动」默认勾选。点击预览中的元素格，程序会显示选中框，切换到「图形化标注」页，并选中输入框中的现有值，方便直接替换。

- 输入后按回车或点击「应用标注」。热力图只接受有限数值，支持科学计数法（如 `1e3`）。输入文本、`NaN` 或 `Infinity` 时，状态栏会提示错误，原值保留。填写文字时请选择标注图。
- 按 `Esc` 或点击「取消修改」，放弃尚未应用的输入，恢复输入框中的当前值。
- 点击「清除该元素」，或留空后应用，即可清除所选元素的值。
- 按 `Ctrl+Z` 撤销已应用的标注或清除操作。
- 在元素格内按住左键拖动，可调整该元素标注的位置；释放后重新渲染。右键仍用于平移整张预览。
- 「该元素的显示 / 着色 / 位置」可独立隐藏标注、隐藏数据着色、排除自动范围或输入偏移量。「恢复默认」恢复显示和原始位置；这些操作不删除元素数据。
- 固定画幅中，颜色条会显示橙色操作框，可左键拖动；紧裁切模式请在精确尺寸对话框中修改位置。

### 按样图调整

点击预览区「样图对照」，加载 PNG/JPG 或静态自包含 SVG。左侧为参考，右侧是当前预览快照，可分别缩放和平移。修改绘图设置后，点击「手动刷新当前快照」更新右侧；程序不会自动推断样图的数据、隐藏元素或样式。

数值格式与舍入规则分别设置。「十进制四舍五入」会把 0.73925 的四位小数显示为 0.7393；「原脚本浮点舍入」用于复现历史结果。舍入只改变显示，不改原始数据。

### 保存项目与恢复工作

通过「项目 → 保存项目」或 `Ctrl+S` 保存 `.ptproj` 文件，其中记录当前数据、绘图设置、单元素显示与位置和各样式的编辑状态；使用「打开项目」继续编辑。预设默认仅保存/应用样式；勾选「保存 / 加载时包含数据」后才恢复预设数据，这会解除当前 Excel 组关联。仅样式预设没有可恢复的数据。

`Ctrl+Z` 撤销，`Ctrl+Y` 重做。撤销只影响工作区，不删除已经导出的图片。程序提供自动草稿和恢复入口，关闭未保存工作时提示保存。

用户数据目录默认为个人目录下的 `.periodic-table-tool`。开发与验收可用 `PTT_USER_DIR` 指向独立目录，避免影响日常草稿和预设。

### 热力图与文本标注

- 热力图：输入有限数字。NaN、Infinity、重复元素等异常输入会被拒绝。
- 标注图：在自定义图表类型中选择标注图，可填写 `活性中心`、`样品A` 等文本。
- 镧锕展开布局可以显示全部元素；三行块布局将镧锕合并为说明块，不展示这些元素各自的数据。

### 自定义绘图

可以调节布局、图表类型、颜色映射或自定义颜色序列、数值范围、数值格式、字体、格子边框、空值格颜色、图尺寸和输出 DPI。元素符号、原子序数、数值的字号及显示状态可独立设置。

中心值留空时使用线性映射；设置中心值时必须满足 `最小值 < 中心值 < 最大值`。自动范围适合单图探索，多图比较应固定范围。

颜色条支持开关、横向/纵向、标题以及任意数量的刻度与标签。选中刻度可以修改、删除或单独隐藏/恢复，也可统一隐藏全部标签。刻度值控制标注位置，不会自动修改数据的颜色映射范围；重复刻度会被拒绝，超出色标范围时提示检查。

高级设置提供科学计数法、数值单位、边框颜色和粗细、标注水平/垂直偏移、自动换行，以及颜色条位置、长度比例、宽度和间隔。颜色节点可写为 `0:#0000ff;0.3:#ffffff;1:#ff0000`，位置范围为 0～1，可用非等距节点控制颜色过渡。

中文文本会尝试使用系统可用中文字体回退。不同电脑缺少同一字体时，字形可能不同；正式排版建议导出 SVG/PDF 并检查。手动放大字号或偏移标注仍可能造成重叠，请结合预览检查排版。

### 图片质量

- 图尺寸可使用英寸 `12x6` 或毫米 `254x127 mm`。「精确尺寸 / 页边距 / 颜色条」以毫米输入；取消自动选项后启用手动主图区边距或色条尺寸，色条位置以画幅左下角为基准。
- 固定画幅按指定尺寸导出；紧裁切按内容缩小或扩大最终画幅，输出像素不再严格等于画幅乘 DPI。
- PNG 像素尺寸由画幅乘 DPI 决定，例如 12×6 英寸、300 DPI 为 3600×1800 像素。
- SVG/PDF 中的矢量线条和文字不依赖 PNG 的 DPI。
- 自定义图使用固定画幅；原脚本兼容样式可能按原规则裁切留白。
- 很大的画幅和 DPI 会增加内存占用，选择满足用途的分辨率即可。

### 预设

预设保存模式、参数、数据、颜色、颜色条及输出格式/目录。加载后可继续编辑，再保存同名预设更新。旧版预设仍可加载，缺失字段使用当前或默认值。

## 数据格式

可导入 UTF-8 文本、CSV、TSV、JSON，也可粘贴 Excel 中复制的两列数据。第一列是大小写正确的元素符号，第二列是数值或标注。

```text
元素,数值
H,0
C,-1.2
Fe,2.4
Cu,2.1
```

表头可省略，也可用 `element,value`。空行和 `#` 开头的注释行会被跳过。空数值不参与绘图。同一元素不要重复填写。

```json
{"H": 0, "C": -1.2, "Fe": 2.4}
```

标注图示例见 `examples/labels.txt`。Excel `.xlsx` 文件使用导入向导选择工作表和数据区域；也可复制两列数据或另存为 CSV 后导入。

## 兼容样式

共 14 种模式：12 种原脚本样式、1 种色图预览工具和 1 种自定义模式。原脚本兼容选项保留历史数值格式、零值行为和裁切规则；日常修正绘图正确处理零值，并修正已知错误的颜色范围。两者分别验证，兼容模式可能保留旧脚本的局限。

| 模式名称 | 对应原脚本 | 特点 |
| ---- | ---- | ---- |
| 蓝白红·百分比热力图（镧锕三行块） | `Hui_Tu_Chong_gou_1` | 蓝→白→红色图，数值显示为百分比；镧系/锕系为三行标注块 |
| 蓝白红·两位小数热力图 A（镧锕三行块） | `Hui_Tu_Chong_gou_2` | 同上布局，两位小数，数据范围约 -65~-12 |
| 蓝白红·两位小数热力图 B（镧锕三行块） | `Hui_Tu_Chong_gou_3` | 同上布局，两位小数，数据范围约 -27~2 |
| 浅灰底·文本标注图（镧锕三行块） | `Hui_Tu_Min_Cheng_01` | 浅灰格子 + 底部文本标签（如 `3c1`） |
| 橙黄红·整数热力图（黑框·原始版） | `Hui_Tu-1` | 橙黄红色图，整数数值，细黑边框，镧锕展开到第 8/9 行 |
| 橙黄红·整数热力图（黑框·重构版） | `Hui_Tu-2` | 同上色图，重构绘制逻辑 |
| 蓝色系·整数热力图（黑框） | `Hui_Tu-3` | 蓝色系色图，整数数值，细黑边框 |
| 色图预览器（生成全部色图） | `Hui_Tu-4` | 一键生成全部 matplotlib 色图的预览图 |
| 绿色系·原始数值热力图（黑框） | `Hui_Tu-5` | 绿色系色图，原始浮点数值，细黑边框 |
| 红蓝冷暖·两位小数热力图（无框） | `Hui_Tu-6` | 红蓝冷暖色图，两位小数，无边框 |
| 红蓝冷暖·三位小数热力图（无框） | `Hui_Tu8` | 红蓝冷暖色图，三位小数，无边框 |
| 经典蓝白红·三位小数热力图（无框） | `Hui_Tu-9` | 经典蓝→白→红色图，三位小数，无边框 |
| 高亮标注图（深蓝底白字） | `Hui_Tu-7` | 有标注元素深蓝高亮（白字），其余浅灰 |
| 自定义热力图（全部参数可调） | — | 色图、范围、小数位、标题、颜色、颜色条全部可调 |

## 开发与验证

`main.py` 负责应用协调；`ui/` 负责预览和工作区控件；`core/` 负责布局、渲染、数据、字体、预设和保存。

```bash
python -m pip install pytest setuptools
python -m pytest -q
python make_dist.py
```

原始一致性基准已收录在 `tests/fixtures/originals/`，无需访问旧工作区附件。测试包含原图一致性、真实格式导出、异常输入、预览命中与打包完整性。

Windows EXE 构建使用 `build_exe.py` 记录的固定工具链：

```bash
python build_exe.py
```

该脚本要求 Windows CPython 3.14.2 x64，创建独立构建环境并生成 `dist/PeriodicTableTool.exe`。首次构建需要下载依赖。源码 ZIP 由 `make_dist.py` 生成，包含运行模块、示例和测试基准。

打包验收：设置环境变量 `PTT_SMOKE=1` 和 `PTT_SMOKE_EXPORT_DIR`（独立的测试输出目录）后运行 EXE，程序会隐藏窗口，导入测试数据并导出 SVG、PNG、PDF 后退出。EXE 同目录的 `smoke_progress.txt` 应包含三条 `export:` 记录及 `smoke:passed`，同时检查输出目录中的三种文件。

推荐用自动隔离验收脚本，它将 EXE 复制到全新临时目录，检查本轮日志和真实输出文件，成功后记录 EXE 哈希及输出校验信息：

```bash
python verify_exe.py --report output/exe-acceptance.json
```


## Agent 本地 JSON 接口（API v1）

Agent 可通过请求/响应文件创建、检查、修改 `.ptproj` 项目及导出图片。接口是一次调用处理一个请求的本地命令行，不是实时控制 GUI，也没有 HTTP 服务。先安装上述源码运行依赖，在仓库根目录执行：

```powershell
python -m application.agent_api --request request.json --response result.json
```

请求是 UTF-8 JSON 对象，必填 `api_version: 1` 和 `action`，可选 `request_id`（字符串或整数，响应原样返回）。字段名区分大小写，未知请求字段会被拒绝；路径相对于进程当前工作目录解析，而非请求文件目录，建议自动化使用绝对路径。JSON 不接受重复键、NaN 或 Infinity，输入上限为 64 MiB。

源码命令支持 `--request -` 从标准输入读取；省略 `--response` 时将 JSON 写到标准输出。Windows windowed EXE 必须指定响应文件，不能依赖标准输出：

```powershell
$p = Start-Process -FilePath '.\dist\PeriodicTableTool.exe' -ArgumentList @('--agent-request', 'request.json', '--agent-response', 'result.json') -Wait -PassThru -WindowStyle Hidden
$p.ExitCode
Get-Content -Raw -Encoding UTF8 result.json | ConvertFrom-Json
```

退出码 `0` 表示成功，`2` 表示失败。成功响应为 `{"api_version":1,"ok":true,"result":{...}}`；失败响应为 `{"api_version":1,"ok":false,"error":{"code":"...","message":"..."}}`。自动化应同时检查退出码及 `ok`。响应文件不得与请求、项目、另存项目或工作簿同路径；响应文件按指定路径写入，重复使用可能覆盖旧响应，建议每次使用独立文件名。

### 可运行示例

示例位于 [examples/agent](examples/agent)。下面从仓库根目录按顺序运行；`describe` 可独立运行，`export` 和 `inspect` 依赖 `create` 生成的项目：

```powershell
python -m application.agent_api --request examples/agent/describe.json --response output/agent-describe-result.json
python -m application.agent_api --request examples/agent/create.json --response output/agent-create-result.json
python -m application.agent_api --request examples/agent/inspect.json --response output/agent-inspect-result.json
python -m application.agent_api --request examples/agent/export.json --response output/agent-export-result.json
```

首次运行应确保 `output/agent-demo.ptproj` 不存在；再次创建请改用新项目路径。`create.json` 使用中文参数 `热力图`、`四位小数`、`十进制四舍五入`，参数数值也写成字符串。原始数据为 `Fe: 0.7`、`Cu: 0.73925`、`Ni: 0.5`、`H: 0`；四位小数显示时 Cu 为 `0.7393`，舍入不改变原始数据。色标显式设为最小 `0`、中心 `0.5`、最大 `1`，所有数据都在范围内，默认拒绝越界的导出可直接成功。

`update.json` **是模板，不能原样运行**：先执行 `inspect`，将 `expected_revision` 的 `REPLACE_WITH_INSPECT_RESULT_REVISION` 替换为响应中的 `result.revision`。以下命令生成替换后的请求，再另存项目（目标必须不存在）：

```powershell
$inspection = Get-Content -Raw -Encoding UTF8 output/agent-inspect-result.json | ConvertFrom-Json
if (-not $inspection.ok) { throw 'inspect 失败，请检查响应' }
$update = Get-Content -Raw -Encoding UTF8 examples/agent/update.json | ConvertFrom-Json
$update.expected_revision = $inspection.result.revision
$update | ConvertTo-Json -Depth 30 | Set-Content -Encoding UTF8 output/agent-update-request.json
python -m application.agent_api --request output/agent-update-request.json --response output/agent-update-result.json
```

### 推荐工作流：describe → inspect → validate → update 另存 → export

对于已有项目，先用 `describe` 查询契约、参数选项和默认值，再 `inspect` 读取项目与 revision；新项目可先运行上面的 create 示例。随后用 `validate` 试算计划修改，检查返回的 `document`、`resolved_style` 和 `warnings`；确认后将相同 `patch`、`dataset_id`（如有）和基准 revision 交给 `update`，通过 `output_project` 另存，最后导出另存项目。

[validate.json](examples/agent/validate.json) 可在 create 后直接运行，不含 revision 占位符；生产工作流建议补入刚读取的 `expected_revision`，确保试算基于预期版本。它和 update 模板使用相同 patch。单独运行该文件前，必须先在仓库根目录执行 `python -m application.agent_api --request examples/agent/create.json --response output/agent-create-result.json` 创建 `output/agent-demo.ptproj`；然后执行 `python -m application.agent_api --request examples/agent/validate.json --response output/agent-validate-result.json`。create 目标已存在时请直接检查该项目，或先统一调整示例项目路径。以下接在 inspect 命令之后运行（代替上面的直接 update 步骤）：

```powershell
$inspection = Get-Content -Raw -Encoding UTF8 output/agent-inspect-result.json | ConvertFrom-Json
if (-not $inspection.ok) { throw 'inspect 失败，请检查响应' }
$validation = Get-Content -Raw -Encoding UTF8 examples/agent/validate.json | ConvertFrom-Json
$validation | Add-Member -NotePropertyName expected_revision -NotePropertyValue $inspection.result.revision
$validation | ConvertTo-Json -Depth 30 | Set-Content -Encoding UTF8 output/agent-validate-request.json
python -m application.agent_api --request output/agent-validate-request.json --response output/agent-validate-result.json
$checked = Get-Content -Raw -Encoding UTF8 output/agent-validate-result.json | ConvertFrom-Json
if (-not $checked.ok) { throw 'validate 失败，请检查响应' }
$checked.result | ConvertTo-Json -Depth 30
```

检查试算结果后执行以下命令。这里仅为无 warnings 的情况继续；有警告时先调整 patch 并重新 validate。

```powershell
if (@($checked.result.warnings).Count -gt 0) { throw '请先处理 validate 返回的 warnings' }
$update = Get-Content -Raw -Encoding UTF8 examples/agent/update.json | ConvertFrom-Json
$update.expected_revision = $checked.result.base_revision
$update.patch = $validation.patch
$update | ConvertTo-Json -Depth 30 | Set-Content -Encoding UTF8 output/agent-update-request.json
python -m application.agent_api --request output/agent-update-request.json --response output/agent-update-result.json
$saved = Get-Content -Raw -Encoding UTF8 output/agent-update-result.json | ConvertFrom-Json
if (-not $saved.ok) { throw 'update 失败，请检查响应' }
$export = Get-Content -Raw -Encoding UTF8 examples/agent/export.json | ConvertFrom-Json
$export.project = $saved.result.project
$export | Add-Member -NotePropertyName expected_revision -NotePropertyValue $saved.result.revision
$export | ConvertTo-Json -Depth 30 | Set-Content -Encoding UTF8 output/agent-export-updated-request.json
python -m application.agent_api --request output/agent-export-updated-request.json --response output/agent-export-updated-result.json
```

`validate` 不保存项目、不导出图片，也不预留写锁；命令的响应文件仍会按 `--response` 写出。`base_revision` 是源文件的指纹，不是试算文档的新修订。校验成功仍可能带 warnings，也不保证之后写入一定成功；文件改变后 update 会拒绝旧 revision，应重新 inspect → validate。

### Actions 与字段

各 action 的字段（公共字段除外）如下；用 `describe` 获取当前实现支持的字段、样式 ID、默认 payload 和并发提示。

| action | 字段与行为 |
| --- | --- |
| `describe` | 无额外字段；返回 `actions`、`patch_fields`、`default_payload`、`styles`、`parameter_choices`、`parameter_defaults`、`display_defaults`、`concurrency`。 |
| `create` | 必填 `project`；可选 `patch`，从默认自定义模式创建新项目。 |
| `inspect` | 必填 `project`；返回 `project`、`revision`、原始 `document`、解析后的 `resolved_style`、`warnings`。创建和更新也返回这些信息。 |
| `validate` | 必填 `project`；可选 `expected_revision`、`patch`、`dataset_id`。按 update 相同顺序在内存中选择数据组、应用 patch 并校验，返回 `dry_run: true`、`base_revision`、`document`、`resolved_style`、`warnings`（以及源 `project`），不写项目文件。 |
| `update` | 必填 `project`、`expected_revision`；可选 `output_project`、`patch`、`dataset_id`。`dataset_id` 选择项目内已有 Excel 数据组，再应用 patch。 |
| `excel_preview` | 必填 `workbook`；不传字符串 `sheet` 时返回工作表列表和 `status: choose_sheet`。传工作表名后预览矩阵，可选区域与方向，返回状态、数据组和统计信息，不修改项目。 |
| `import_excel` | 必填 `project`、`expected_revision`、`workbook`、`sheet`；可选 `output_project`、区域与方向、`dataset_index`（从 0 开始，默认 0）。预览须为 `ready`，追加全部解析数据组并选择指定组，返回 `import_stats`、`dataset_ids`。不修改原工作簿。 |
| `export` | 必填 `project`；可选 `expected_revision`、`output_dir`、`formats`、`base`、`allow_out_of_range`。导出当前项目数据，不修改项目。 |

Excel 区域字段为 `elements_range`（默认 `B1:AG1`）、`conditions_range`（默认 `A2:A6`）、`values_range`（默认 `B2:AG6`）；`direction` 为 `matrix_rows`（默认，条件按行）或 `matrix_columns`（条件按列）。先预览检查工作表、区域、解析状态和数据组，再导入；公式只读取工作簿已保存的结果。

`export.formats` 为不重复且非空的 `png`、`svg`、`pdf` 列表，省略时使用项目输出格式。`base` 默认 `periodic_table`，限 1～80 个字母、数字、下划线或连字符。请显式指定 `output_dir`。响应 `result.files` 列出每个文件的绝对 `path`、`bytes` 和 `sha256`。所有导出图片使用 `auto_name` 添加时间戳及必要序号，避免覆盖已有图片。空数据拒绝导出；越界数据或颜色条刻度默认返回 `RANGE_WARNING`，应先调整范围，只有明确接受越界时才设 `allow_out_of_range: true`。

### Patch 合并与单元素控制

`patch` 支持 `mode_id`、`params`、`display`、`data`、`replace_data`、`element_overrides`、`show_cbar`、`show_cbar_labels`、`cbar_override`、`custom_colors`、`compatibility`、`output_format`、`output_dir`。完整默认结构见 `describe.result.default_payload`；参数选项见 `parameter_choices`，参数默认值见 `parameter_defaults`，显示默认值见 `display_defaults`（均位于 `describe.result`）；样式 ID 使用 `describe.result.styles` 中的值。

- `params`、`display` 浅合并：只更新提供的键。`params` 所有值均为字符串，选项使用中文界面原值；例如 `fmt: "四位小数"`、`rounding: "十进制四舍五入"`。`display` 的 `show_symbol`、`show_number`、`show_value`、`transparent` 为布尔值。
- `data` 默认按元素符号合并；例如 `{"Fe":0.75,"H":null}` 修改 Fe 并删除 H。`replace_data: true` 会整体替换数据，必须同时提供 `data` 对象；`data: {}` 可清空。零是有效数据，热力图数值必须有限。
- `element_overrides` 按元素合并，每个元素内部再合并所提供字段；`{"Fe":null}` 删除 Fe 的全部覆盖配置、恢复默认。空对象不会清除旧覆盖，单字段不能用 null 重置。
- 每元素 `show_value` 控制标注可见性，`show_color` 控制数据着色，`include_in_range` 控制是否参与自动范围，三者为独立布尔开关，隐藏不会删除数据；排除自动范围不会自动改变固定色标或免除着色数据的越界检查。`value_dx`、`value_dy` 为有限数字偏移量（与 `params` 中的字符串类型不同）。
- 其他 patch 字段整体替换。切换 `mode_id` 时恢复该模式已保存的样式或默认样式，并保留当前数据，再应用其余 patch。

### 画幅、位置与颜色参数示例

以下字段中，`figsize`、`margins`、`cbar_box` 位于 `patch.params`，必须写成字符串；`show_cbar`、`cbar_override`、`custom_colors` 位于 `patch` 顶层，使用 JSON 布尔、对象或数组。

| 字段 | 输入格式与空值含义 |
| --- | --- |
| `params.figsize` | 宽×高；`"10x5"` 为英寸，`"254x127 mm"` 为毫米，两者等价（1 英寸 = 25.4 mm）。宽度限 2～40 英寸，高度限 1～40 英寸；不能用空串自动。 |
| `params.margins` | 归一化主图区边界 `"left,bottom,right,top"`，例如 `"0.05,0.08,0.85,0.95"`；不是四边留白宽度。以画幅左下角为原点，满足 `0 ≤ left < right ≤ 1`、`0 ≤ bottom < top ≤ 1`。`""` 恢复自动布局。 |
| `params.cbar_box` | 归一化颜色条位置与大小 `"x,y,w,h"`，例如 `"0.9,0.15,0.025,0.7"`；以画幅左下角为原点，宽高为正，整个矩形须位于画幅内。`""` 恢复自动位置和尺寸。 |
| `show_cbar` | 布尔值 `true` / `false`，显示或隐藏整个颜色条；不是字符串，也不放在 params 内。 |
| `cbar_override` | 对象：`ticks` 为有限数字数组，`labels` 为字符串数组，`visible` 为布尔数组，三者长度相同；刻度不得重复。`fontsize` 为正数。`visible` 可省略（全部可见），`fontsize` 可省略（默认 8）；`null` 恢复样式默认颜色条。 |
| `custom_colors` | 至少两个 RGB 三元数组，每个分量为 0～1 数字，例如 `[[0,0,1],[1,1,1],[1,0,0]]`，不是 0～255 或颜色字符串。将 `params.cmap` 设为 `"自定义(蓝-白-红)"` 或 `""` 时采用该颜色序列；`params.color_nodes` 非空时会优先使用颜色节点。 |

省略 patch 字段会保留原值；需要恢复自动布局时显式发送 `"margins":""`、`"cbar_box":""`，恢复默认颜色条时发送 `"cbar_override":null`。`params.vcenter: ""` 表示不用中心值、改用线性映射；不要将所有空默认参数一律替换成 `0`。精确定位建议搭配 `crop_mode: "固定画幅"`，避免紧裁切改变最终画幅。

下面是可放入 create、validate 或 update 请求的 `patch` 示例（仅为 patch，不是完整请求文件）。色条刻度均在 0～1 范围内；`visible: false` 隐藏对应刻度及标签，保留配置；`show_cbar_labels: false` 则统一隐藏全部标签。

```json
{
  "params": {
    "figsize": "254x127 mm",
    "crop_mode": "固定画幅",
    "margins": "0.05,0.08,0.85,0.95",
    "cbar_box": "0.9,0.15,0.025,0.7",
    "vmin": "0",
    "vcenter": "0.5",
    "vmax": "1",
    "cmap": "自定义(蓝-白-红)",
    "color_nodes": ""
  },
  "show_cbar": true,
  "show_cbar_labels": true,
  "cbar_override": {
    "ticks": [0, 0.5, 1],
    "labels": ["低", "中", "高"],
    "visible": [true, false, true],
    "fontsize": 8
  },
  "custom_colors": [[0, 0, 1], [1, 1, 1], [1, 0, 0]]
}
```

### 修订与并发

`update` 和 `import_excel` 必须先 `inspect`，将其 `result.revision` 原样作为 `expected_revision`；另存也必须提供。revision 是项目文件字节的 SHA-256 指纹，文件改变后旧 revision 会导致 `REVISION_CONFLICT`，应重新检查并决定如何合并。`validate`、`export` 可选传 `expected_revision`，分别确认试算和导出基于预期版本；推荐 validate 也传入 inspect 的 revision。

建议用新的 `output_project` 另存，保留输入项目。`create` 和另存不会覆盖已有项目，冲突返回 `OUTPUT_EXISTS`；它们不会像导出图片一样自动改名。省略 `output_project` 或设置为源路径会原位更新：写入前检查文件指纹，并用 `.agent-lock` 锁串行化配合此协议的 API 写入者，锁占用时返回 `PROJECT_BUSY`。

GUI 不参与该锁，也不会实时同步外部修改。原位修改前请先保存并关闭 GUI 中的同一项目；修改后重新打开或重载文件，再继续编辑，避免 GUI 内存中的旧状态覆盖 Agent 结果。
