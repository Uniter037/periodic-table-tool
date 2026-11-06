# A00 首批公共契约（冻结 v1）

冻结日期：2026-11-05。消费方：A01（读取、映射、导入）与 A03（状态、命令）。本文是本批字段、默认值、错误语义和事务交接的规范；依据 [02-architecture](02-architecture.md)、[05-diagnostics](05-diagnostics.md) 及当前 `application/state.py`。草案未明确之处以本文的显式选择为准；后续变更须由 A00 同步消费方、序列化与验收资料，不能各自添加同名异义字段。

本次交付只有此文档，不代表实现、测试或 M0 已完成。完整项目 JSON Schema、schema1/2 golden fixtures、StyleDescriptor 及回归基线仍属于后续 A00 交付；下面的 JSON 是规范示例，未声称已通过程序验证。首批域类型归 `domain/data.py`、`domain/mapping.py`、`domain/diagnostics.py`，跨层端口唯一归 `application/ports.py`；A01/A03 不在各自模块复制公共定义。

## 1. 通用编码与默认值

- DTO 仅含 JSON 对象、数组、字符串、有限数、布尔、null。数值字段拒绝 bool、NaN、Infinity；ID 为非空、不含业务含义的稳定字符串，无自动生成默认值。名称修改不改变 ID。新 ID 由应用层分配，转换过程对同一预览复用已分配 ID。
- 表中“必填”表示缺失即错误；`null` 与字段缺失不同。标为有默认值的字段可在输入边界省略，解码后补齐，编码时全部输出。默认容器每个实例独立。禁止在 Store 的 validator 中补默认值：必须在事务前显式规范化。
- 未知核心字段拒绝，禁止静默忽略。首批四种 DTO 不设自由扩展袋；项目级扩展只能放架构规定的命名空间 `extensions`，不是任意 DTO 的旁路。
- CellValue、Dataset、Diagnostic 无独立版本字段，随项目 schema=2 或本批应用 DTO 协议版本 1；ImportMapping 自带 schema_version=1。未知版本拒绝。时间采用 UTC `YYYY-MM-DDTHH:mm:ss[.fraction]Z`；hash 为原始字节 SHA-256 的 64 位小写十六进制。
- 映射/数据内容 hash 使用 UTF-8 JSON，`ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False`，不自行把 1.0 改成 1、不修剪字面串。此规则与当前 Store 编码对齐。source_hash 则基于来源文件字节，不用 mtime 代替。
- 领域对象、预览与快照在边界须深度隔离；仅 frozen dataclass 不能保证内部 dict/list 不变。UI、订阅者、调用者均不得通过引用修改 Store。

## 2. CellValue 与可定位来源

### 2.1 字段

| 字段 | 类型 | 默认 | 约束 |
|---|---|---|---|
| kind | number / text / missing / error | 必填 | 区分零、空白、字面文本和错误 |
| raw_text | string 或 null | null | 原始字面文字；不由 numeric 反推，不受显示精度修改 |
| numeric | number 或 null | null | 有限 int/float，且不是 bool |
| formula | string 或 null | null | Excel 原始公式（含 `=`）；只作来源信息，不执行 |
| cached | number / string / boolean / null | null | 原始已保存公式结果；不是缓存存在与否的布尔标记 |
| format_code | string 或 null | null | Excel 格式代码；不把显示格式当数值转换 |
| source | CellRef 或 null | null | 手工输入、不可定位文本可为 null |

CellRef 三个字段全部必填：`source_id: ID`、`sheet: 非空字符串`、`address: 单个A1坐标`。sheet 精确匹配工作表名；address 使用无 `$` 的大写坐标（如 B2），不含 sheet、范围或 UI 像素。非 Excel 文本不得伪造工作表或 A1 坐标；行号说明可写在面向用户的诊断文案中。

### 2.2 组合不变量

| kind | numeric | raw_text | 语义 |
|---|---|---|---|
| number | 必须有限且非 null | 可 null | 原生 Excel 数值通常无可信原始字面串，保留 null；文本经显式解析后保留原串 |
| text | 必须 null | 必须字符串，可为 `""` | `"001"`、`"0"` 不自动转数值；category 使用此 kind |
| missing | 必须 null | 可 null 或字符串 | 未提供值；显式转换为空值时仍保留原串 |
| error | 必须 null | 可 null 或字符串 | 读取/转换失败，至少有一条 error 诊断定位对应单元格或记录 |

- 无公式时 cached 必须 null。有公式时 raw_text 不用于重复保存公式，公式仅放 formula；numeric/raw_text 是映射转换后的有效结果，cached 保留转换前缓存。数值缓存 0 和文本缓存 `""` 均不是缓存缺失。
- 默认 `cached_only`：数值缓存产生 number；字符串缓存产生 text；无缓存产生 error + `FORMULA_CACHE_MISSING`；Excel 错误缓存产生 error + `CELL_ERROR`。缓存结果使用时给出 `FORMULA_CACHE_USED` warning（按区域合并），提醒可能未刷新。
- 布尔和日期默认保留为 text（布尔用 `TRUE`/`FALSE`，日期用 ISO-8601 文本），不隐式转热图数值。若读取库返回日期对象，不把对象塞入 DTO。首批没有日期转数值步骤，numeric 指标遇到这些值以 `VALUE_KIND_MISMATCH` 拒绝；布尔公式缓存仍可保留 bool，但不进入 numeric。
- 原始空单元格为 missing；显式空字符串为 text。trim 后空串仍是 text，numeric_parse 不把空串改成 0。缺失记录不得在领域层删除；只有 legacy 渲染适配可略去。
- error 是可展示的预览值，不得进入成功提交的数据集。单元格原文可能含敏感信息，只保留在业务 DTO；不得直接写日志。

## 3. Dataset 与引用完整性

| 字段 | 类型 | 默认 | 约束 |
|---|---|---|---|
| id | ID | 必填 | 项目内 datasets 集合唯一 |
| metric_id | ID | 必填 | 指向现存或同事务创建的 Metric |
| condition_id | ID | 必填 | 指向现存或同事务创建的 Condition |
| records | object：元素符号 → ElementRecord | 必填 | 至少一条；仅内置元素表的规范符号 |
| provenance | Provenance | 必填 | 来源快照信息，不是可变文件的当前状态 |

ElementRecord：`element` 必填且等于 records 键；`value: CellValue` 必填；`attributes: {稳定字段ID: CellValue}` 默认 `{}`。主值的 field_id 固定为 `value`，attributes 禁止使用此保留键。元素名称不得作为任意属性 ID。同一组一个元素仅一条；解析时先检测重复，不能用 dict 后写覆盖前写。

Provenance 固定四字段：`mapping_id: ID|null` 必填、`source_hash: SHA256|null` 必填、`transform_version: string` 必填、`created_at: UTC时间` 必填。首批转换器版本固定 `import-v1`。A01 导入时前两项非 null，mapping_id 指向本项目已保存/同事务新增的映射，该映射再指向 source；手工或迁移数据允许两项同时 null，转换版本须明确如 `manual-v1`/`migration-v1`，不能假造来源。created_at 由应用层创建预览时传入，重试转换不得重新取当前时间。

Metric 最小依赖：`id, name, value_kind` 必填，`unit=null`；value_kind=numeric/text/category。Condition 最小依赖：`id, label` 必填，`attributes={}`；首批属性为属性名到 CellValue 的映射，条件单位由映射 condition.unit 表达。标签相同不表示 ID 相同，不按标签隐式合并。numeric 指标只接受 number/missing；text/category 只接受 text/missing。

Dataset 是**来源快照**。effective 值由 `(dataset_id, element, field)` 上的 Override.value 覆盖快照；无覆盖取快照值。Override.base_value 保存修改时的源值，missing 也可被显式覆盖。A03 的 EditValue 写覆盖，不改源 records；显示精度和样式也不改 records。未映射到的元素不强制补齐 118 项，已映射元素的空值必须建 missing 记录。

## 4. ImportMapping v1

### 4.1 顶层与公共策略

| 字段 | 类型 | 默认 |
|---|---|---|
| id, source_id | ID | 必填 |
| schema_version | integer，固定 1 | 必填 |
| layout | matrix_rows / matrix_columns / records / category_groups | 必填 |
| regions | 对应布局的对象，见下 | 必填 |
| metric | `{name:非空字符串, unit:string|null, value_kind:numeric/text/category}` | 对象必填；unit=null，其余必填 |
| condition | `{name:非空字符串, unit:string|null, interpretation:literal/percent_points/fraction}` | 对象必填；unit=null，interpretation=literal |
| policies | 策略对象 | `{duplicate:"error", missing:"keep", hidden:"include", formula:"cached_only"}` |
| transforms | 按序 Transform 数组 | `[]` |

policies 中各字段可省略并补上述默认值。duplicate 首批只接受 error；显式聚合见 transforms，不开放 first/last 静默覆盖。missing 首批只接受 keep；hidden 接受 include/exclude；formula 首批只接受 cached_only。其他值均报 `MAPPING_INVALID`，不降级。映射描述符不携带 metric_id/condition_id；应用预览阶段创建目标 ID，提交时整体保存对应对象。

condition.interpretation 控制条件属性：literal 保留文本或原生类型，percent_points 的 25 表示 25%，fraction 的 0.25 表示 25%；数值属性统一存比例点（fraction ×100），原文字段保留。数值解释遇到不可解析条件报 `NUMERIC_PARSE_FAILED`。不得把这里的解释应用于测量值；测量值缩放必须声明 percent_scale。

Region 固定 `{sheet:string, range:string}`，均必填。range 为无 `$` 的大写闭区间 A1 或 A1:B2，必须位于格式支持的地址边界；空的有效单元格不是越界。不得用已用区域裁掉尾部空值。矩阵与记录布局各自区域同 sheet；合并单元格与任何被消费区域相交即 `MERGED_REGION_UNSUPPORTED`，首批不做向下填充。

### 4.2 四类布局的精确字段

| layout | regions 允许的字段 | 转换规则 |
|---|---|---|
| matrix_rows | elements:Region, conditions:Region, values:Region，全部必填 | elements 是单行，conditions 是单列；values 宽=元素数、高=条件数；每条件行生成一组 |
| matrix_columns | elements:Region, conditions:Region, values:Region，全部必填 | elements 是单列，conditions 是单行；values 高=元素数、宽=条件数；每条件列生成一组 |
| records | sheet:string, start_row:int, end_row:int, columns:对象，全部必填 | 行号从1起，包含两端；列使用大写字母，如 A、AA；不含表头；按条件值分组 |
| category_groups | groups:数组，必填且非空 | 每个分组条目显式指定类别单元格和元素范围；按 group_name 分组，无名称时全部进入同一组 |

records.columns 固定 `element:列字母`、`value:列字母` 必填，`condition:列字母|null=null`，`attributes:{field_id:列字母}={}`。列角色不得重叠；condition=null 时使用 condition.name 作为唯一组的标签。condition 列存在时按 CellValue 的 kind+numeric/raw_text（不含来源）精确分组，不按浮点格式化显示文字合并；条件空白报 `CONDITION_MISSING`。无表头导入通过显式列与 start_row 实现，不猜测首行。

category_groups 的每个条目固定：`category:Region`（单个单元格，必填）、`elements:Region`（单行或单列，必填）、`group_name:string|null=null`。类别值必须为非空文本，metric.value_kind 必须 category；每个有效元素生成以类别为 text 的 value，source 指向 category 单元格，元素标签问题定位 elements 对应单元格。group_name=null 时用 condition.name；相同组名归同组。不同类别中同元素属于同组时仍是重复错误，不隐式多标签。类别为空报 `CATEGORY_MISSING`。

空元素标签且对应值/属性全部空时可跳过并统计；标签空而值存在报 `ELEMENT_MISSING`。元素只接受内置表规范符号；可先显式 trim/case，不能自动模糊识别。隐藏策略 exclude 按完整记录/矩阵对应轴一致过滤元素、条件、值；先校验原始形状再过滤，禁止过滤后错位拼接。include 默认保留并给区域级 `HIDDEN_INCLUDED` info。过滤后无组/无记录报 `EMPTY_DATASET`。

### 4.3 声明式转换

每一步固定 `{op:string, target:string, params:object}`，三项必填。target 只能为 `element`、`condition`、`value` 或 `attributes.<field_id>`；属性必须在 records.columns.attributes 中声明。步骤按数组顺序作用，参数不接受额外键。不支持任意表达式、eval、脚本或隐式区域。

| op | params | 规则 |
|---|---|---|
| trim | `{}` | 去文本两端空白，raw_text 仍保存最初原串；element/condition 另持转换后的分组键 |
| case | `{mode:"upper"/"lower"/"element_symbol"}` | 显式大小写转换；element_symbol 首字母大写其余小写；仅用于 element/condition，不改 CellValue 原文 |
| numeric_parse | `{}` | 仅用于 value/attributes；解析去两端空白后的十进制及科学计数，`.` 为小数点，不接受千分位、百分号、布尔、NaN/Infinity；保留 raw_text |
| percent_scale | `{factor:有限非零数}` | 仅 number 的 value/attributes；如 fraction→百分数用100；不得凭 format_code 自动缩放 |
| round | `{digits:integer}` | digits ∈ [0,15]；仅 number 的 value/attributes，Python round 半偶舍入；这是显式数据转换，不是显示格式 |
| aggregate | `{method:"sum"/"mean"/"min"/"max"}` | target 必须 value，步骤必须唯一且最后；显式允许同条件同元素的 number/missing 重复聚合 |

trim 对 value/attributes 的效果仅作为后续解析的工作文本；若最终仍为 text，则其有效文本与原始文本不能在当前 CellValue 中分别存放，因此首批拒绝这种组合（`TRANSFORM_INVALID`），不得覆盖 raw_text。case 同理仅开放键字段。此限制避免字段不够时私加 display_text/text 字段。

所有数值变换传播 missing，不把缺失补零；error 保持并阻止提交。聚合忽略 missing，全 missing 仍为 missing；非数值拒绝；重复项带非空 attributes 首批拒绝聚合以免丢失属性。聚合值 source/raw_text/formula/cached/format_code 均为 null，溯源通过 mapping_id、source_hash 和映射选区复算，诊断 `DUPLICATES_AGGREGATED` 列出参与位置。未声明 aggregate 时 duplicate=error；声明后只放行满足该规则的重复。聚合或缩放溢出报 `NON_FINITE_NUMBER`。

## 5. Diagnostic 与首批稳定代码

### 5.1 领域诊断字段

| 字段 | 类型 | 默认 | 规则 |
|---|---|---|---|
| code | 下表稳定字符串 | 必填 | 调用方按 code 分支，禁止解析 message |
| severity | info / warning / error | 必填 | 不从日志级别隐式推导 |
| message | 非空字符串 | 必填 | 可本地化，给用户的事实描述 |
| locations | CellRef 数组 | `[]` | 多个冲突位置均保留；无位置时空数组，不虚构 A1 |
| target | DiagnosticTarget 或 null | null | 无文件坐标时定位映射/记录/命令字段 |
| remedy | string 或 null | null | 可操作建议，无建议时 null |

DiagnosticTarget 固定 `{kind, id, path}`：kind=mapping/dataset/plot/project/command；id 为对象 ID 或 null（尚未创建/命令时）；path 为相对该对象的 RFC6901 JSON Pointer，根为 `""`。三项全部必填，例如 `{kind:"mapping",id:"map-1",path:"/regions/values"}`。

Diagnostic 不增加 exception/stack/details/error_id 字段。运行日志是独立协议：A12 按 05-diagnostics 的 event_code、trace_id、error_id 等记录，边界可将 Diagnostic.code 作为 event_code 并在任务错误信封关联 error_id。业务诊断不依赖 logging，关闭日志仍返回全部诊断。异常在责任边界记录一次；不能直接序列化 CellValue、完整映射、绝对路径或原始异常文案进入日志。代码不能被重用为另一含义；扩充代码须同步此表。

### 5.2 稳定代码表

除表内注明外 severity 固定 error。任何 error 均阻止当前预览提交/命令，不自动删除错误记录后继续成功。

| code | 触发条件与处置 |
|---|---|
| DTO_INVALID | 类型、必填、未知字段或 CellValue 组合不合法；修正输入 |
| SCHEMA_UNSUPPORTED | 项目/映射版本不支持；保留原件，升级或迁移 |
| ID_DUPLICATE | 同类型集合 ID 重复；重新分配并更新引用 |
| REFERENCE_INVALID | metric/condition/source/mapping/plot/dataset/属性引用不存在 |
| SOURCE_UNREADABLE | 文件不存在、权限不足或读失败；重新选择或重试 |
| SOURCE_INVALID | 文件损坏、签名不符或格式不支持；不返回成功空表 |
| SOURCE_CHANGED | 公式视图与缓存视图不属同一字节快照；重新读取 |
| READ_LIMIT_EXCEEDED | 文件/解压/条目/选区预算超限；缩小选区或显式调整配置 |
| SHEET_NOT_FOUND | 工作表名不存在 |
| REGION_INVALID | A1语法、记录行列、地址边界不合法 |
| MAPPING_INVALID | 布局字段、策略、角色或类别指标不合法 |
| MAPPING_SHAPE_MISMATCH | 矩阵元素/条件轴与值区尺寸不符 |
| MERGED_REGION_UNSUPPORTED | 被消费区域包含合并单元格 |
| TRANSFORM_INVALID | 未知转换、非法参数/target/顺序/组合 |
| NUMERIC_PARSE_FAILED | 显式数值解析失败；保留原串 |
| NON_FINITE_NUMBER | 输入或变换结果为非有限数 |
| VALUE_KIND_MISMATCH | 有效值与指标或转换要求不符 |
| ELEMENT_MISSING | 缺元素键但存在数据 |
| ELEMENT_UNKNOWN | 非内置元素符号，禁止静默过滤 |
| ELEMENT_DUPLICATE | 同条件同元素重复且无合法显式聚合；列出冲突位置 |
| CONDITION_MISSING | 所需条件单元格为空 |
| CATEGORY_MISSING | 类别单元格无有效文本 |
| EMPTY_DATASET | 选区/策略结果无可提交记录 |
| CELL_ERROR | Excel错误值或无法表示的读取结果 |
| FORMULA_CACHE_MISSING | 公式无保存结果；先在电子表格应用重算并保存 |
| FORMULA_CACHE_USED | warning：使用已保存缓存，不保证最新 |
| HIDDEN_INCLUDED | info：按默认策略包含隐藏行/列 |
| DUPLICATES_AGGREGATED | warning：按显式步骤完成聚合 |
| SCAN_TRUNCATED | warning：候选扫描达到200×200上限；可手动指定区域，不能宣称整表为空 |
| IMPORT_CANCELLED | info：用户取消；不提交、不返回部分成功 |
| PREVIEW_INVALID | preview_id 不存在、被消费或来源/映射hash失效；重新预览 |
| REVISION_CONFLICT | expected_revision 与当前不同；保留项目，重新预览/执行 |
| IMPORT_BLOCKED | 预览有 error；返回原诊断并拒绝提交 |
| COMMAND_INVALID | 未知命令/模式、非法参数或非法覆盖目标 |
| STATE_REENTRANT | 通知回调期间请求事务；由控制器排队到通知结束后 |
| DATASET_MISMATCH | 预览/单图导出参数与活动 PlotSpec.dataset_id 不一致 |
| COMMAND_FAILED | 未预期的命令实现异常；保留原状态，用户文案不泄露异常内容 |
| OBSERVER_FAILED | warning：事务已提交但订阅回调失败；不得报告提交失败或自动重放 |

同一诊断可对应多位置；面向用户保留具体位置，日志只记录允许的计数/阶段/code。取消不因 severity=info 而可提交：预览状态必须单独标记 cancelled。

## 6. A01 → A03 的可实施交接

### 6.1 读取与预览边界

沿用架构端口：`inspect(source, cancel)`、`read_region(source, region, cancel)`；reader 只读，作业结束/取消均关闭文件。公式视图和 data_only 视图必须读同一稳定副本，hash 验证通过才交付。只对明确映射区域转换；候选发现结果不自动提交，不能把 ROUND 辅助区纳入值区。建议初始文件50MB、累计解压500MB、选区100万格；具体压缩条目数上限由读取配置显式提供，不能视作无界。

首批辅助 DTO：CellGrid=`{region:Region, source_hash:SHA256, cells:CellValue[][]}`，行优先，必须矩形且包括每个空格，每个 Excel 单元格携带真实 CellRef。hidden/merged 信息由读取结果的内部元数据供布局校验，不添加到 CellValue；A01 必须在生成预览前完成检查。SheetSummary/WorkbookSummary 的全字段另由 A00 补充，不以本文声称其已完全冻结。

`preview(mapping, grids) -> ImportPreview` 为无项目副作用的操作。首批 ImportPreview 字段全部必填：

| 字段 | 类型/含义 |
|---|---|
| preview_id | 应用分配的不透明 ID |
| status | ready / invalid / cancelled；只有 ready 可提交 |
| base_revision | 创建预览时的非负 Store.revision |
| mapping_hash | 补齐默认值后的完整映射规范 JSON hash |
| source_hash | 本次读取的稳定字节快照 hash；各 grid 必须一致 |
| mapping | 规范 ImportMapping 快照 |
| sources, metrics, conditions, datasets | 待创建的对象数组；预览中所有引用闭合或指向 base_revision 中已存在对象 |
| diagnostics | Diagnostic 数组 |
| stats | `{dataset_count, record_count, number_count, text_count, missing_count, error_count, skipped_blank_count}`，全部非负整数 |

stats 的 record_count 是输出主记录数，等于四种 kind 计数之和，不计 attributes；error_count 是主值 kind=error 的数量，不能代替 error 诊断计数。invalid 可携带部分候选用于定位，不能提交；cancelled 的 datasets=[]、输出计数为0，不发布半份结果。空有效结果也属于 invalid。源 SourceRef 沿用架构的 id/kind/display_name/locator/fingerprint，A01 不把打开的工作簿/句柄放进 sources。

原架构 `preview(mapping, grids)` 未传 revision/时钟：应用 ImportService 创建预览时从注入的 Store、ID分配器和时钟取得上下文，再调用纯转换器；不可由 domain 读取全局 Store 或系统时钟。preview 返回的对象是副本，服务内部保存独立候选，commit 不接受调用方回传的 datasets。修改映射、重新读取/重新链接来源、明确检测到原文件变化或更换项目均使旧预览失效；不要求为了离线快照提交而重新打开原文件。

### 6.2 提交签名、模式与原子性

`commit(preview_id: str, expected_revision: int, mode: ImportCommitMode) -> CommandResult`

首批 ImportCommitMode 是 JSON 对象 `{kind:"append", activate_dataset_id:ID|null}`，activate_dataset_id 默认 null。其他 kind 返回 COMMAND_INVALID；替换、覆盖和源刷新留给 A04，不能复用 append 暗中替换现有组。

顺序：检查通知重入 → 检查 expected_revision=当前 revision=base_revision → 检查预览有效/hash/状态 → 检查无 error → 检查 ID/引用 → 构建候选 → 一次 Store.transact。expected_revision 必填且非 bool 的非负 int。激活 ID 非 null 时必须属于本次候选 datasets，项目必须已有有效 active_plot_id；同事务只改活动图形 dataset_id。null 时不改当前绘图组，也不自动创建图形。无活动图形仍可导入后由独立创建图形命令使用。

同事务写入 sources、mappings、metrics、conditions、datasets 和可选激活；已有引用对象可复用，但相同 ID 不同内容拒绝，不允许导入顺便改写旧对象。一次成功消耗 preview_id；失败不消耗，但 revision/source/mapping 失效者仍须重新预览。取消、失败、重复点击已消费预览都不产生历史或脏状态。

CommandResult 固定 `{applied:bool, revision:非负int, diagnostics:Diagnostic[]}`，全部必填。applied 表示实际业务内容变化，不是“调用没有异常”；无变化为 false、当前 revision、通常空诊断。拒绝为 false、当前 revision、有对应诊断；取消为 false+IMPORT_CANCELLED。成功为 true、提交后的 revision，可带 warning/info。已提交后通知失败仍为 true，不可回滚或提示“导入未成功”。

## 7. A03 状态与数据组唯一真值

### 7.1 唯一真值与命令

**当前预览及单张导出的数据组唯一取自 `project.plots[active_plot_id].dataset_id`**（数组存储时按 id 查找）。活动图形不存在时 selector 返回 null，禁用预览/单张导出；有活动图形时 dataset_id 必须引用有效组。

- SessionState 只保存列表高亮/多选等交互信息。禁止新增可被渲染读取的 selected_dataset_id/current_dataset 或复制一份“当前数值”。SelectionChanged 不改 ProjectState、revision、dirty 或撤销历史。
- `SetActiveDataset(dataset_id, expected_revision)` 检查活动图形与目标组存在，只更新该图形 dataset_id；样式、绑定、覆盖及其他图形不变。不同 ID 一次事务、一次撤销；相同 ID 是无变化，不增加 revision。dirty 按保存点 hash 计算，不强制设 true。
- `compile(project, plot_id, dataset_id)` 在预览/单张导出路径必须校验参数等于对应活动图形绑定，否则 DATASET_MISMATCH。批量计划可明确覆盖 dataset_id，但不写回图形/Store，不产生历史。不得用列表高亮作为隐式覆盖。
- 保存包含 active_plot_id 与每个 PlotSpec.dataset_id；重开据此恢复。状态栏组名由同一 selector 解析 Metric/Condition，不另存数据组选择。撤销/重做切换后预览重新读取 selector。
- EditValue 的主字段为 `value`，属性字段为稳定 field_id；不接受随意路径写任意项目字段。对不存在元素或属性的编辑返回 COMMAND_INVALID；新增属性属于显式命令。

### 7.2 与当前 application/state.py 的精确对接

| 现有行为（已读代码，未执行验证） | A03 契约/适配要求 |
|---|---|
| ProjectStore 接受 dict，_prepare 先编码，再用 detached 副本校验，返回原编码 | DTO 规范化在入库前完成；validator 只拒绝，不靠修改参数修复状态；接入域不变量校验 |
| transact 在副本执行 operation，验证通过才更新历史 | 失败保留 snapshot、revision、dirty、历史/重做栈与保存点；不在 operation 内写文件/发事件 |
| 内容编码不变时返回 None | 命令层转为 applied=false；不能凭“没抛异常”返回 true |
| 变化时 revision+1、同步 _notify，返回 Change(revision,command,dirty) | CommandResult 由应用层包装，Change 不能冒充它；不要求修改现有返回类型才能接入 |
| expected_revision 默认 None，通知中执行事务抛 RuntimeError | 用户命令/导入包装层强制传 revision；先显式检查并产生稳定代码，不通过异常中文字符串判断 |
| validator/operation 异常原样抛出 | 已知域错误由应用层映射 Diagnostic；未知异常统一 COMMAND_FAILED 并在边界记录一次；不能所有 ValueError 都归为版本冲突 |
| observer 异常被捕获，仅保留最近20个异常类名 | 已提交事务仍成功；类名列表无法还原堆栈/回调或可靠计算新增数量，A03 接入边界通知包装器记录 OBSERVER_FAILED，不假定现有 Store 已提供结构化诊断 |
| undo/redo 移动快照指针，成功时 revision+1 | revision 单调递增，不恢复旧 revision；无历史时不变，返回 applied=false |
| 相同 merge_key 可合并连续历史，end_edit 结束合并 | 每个实际修改仍 revision+1/通知一次；一个字段编辑会话撤销一次。确认、失焦、拖动结束调用 end_edit；不同对象/字段不得复用键 |
| history_limit=100、history_bytes=64*1024*1024 | 保留当前快照，预算超限淘汰最旧历史；当前单份超过预算仍保留，不谎称总内存硬限64MB |
| dirty 比较当前编码hash与 saved_hash | 撤销到保存内容变干净；成功保存准确那份快照后调用 mark_saved(snapshot)，不能标记后来改动的快照 |
| mark_saved 不增加 revision，但通知 saved 且结束合并 | saved 通知不是 ProjectChanged，不安排无意义数据重算；保存点只在持久化成功后更新 |
| replace 会清空历史并 revision+1；saved=False 设置 saved_hash=None | 仅用于加载/新建/恢复，先完成读取迁移校验再一次替换；不是导入 append。saved=True 是正式已保存项目，恢复草稿用 false |

Store/controller 由同一线程拥有；worker 只返回 DTO，不持有 Store。订阅通知期间的新命令延迟到通知结束后执行，不能让重入改变历史。渲染结果以 revision/data_hash 校验，旧结果不覆盖当前图。

## 8. 规范示例与交接检查（未运行）

以下为完整默认字段的三个单元格示例，分别是零、字面前导零和真正空白；字段不能互换：

```json
[
  {"kind":"number","raw_text":null,"numeric":0,"formula":null,"cached":null,"format_code":"0.00","source":{"source_id":"src-1","sheet":"Data","address":"B2"}},
  {"kind":"text","raw_text":"001","numeric":null,"formula":null,"cached":null,"format_code":"@","source":{"source_id":"src-1","sheet":"Data","address":"C2"}},
  {"kind":"missing","raw_text":null,"numeric":null,"formula":null,"cached":null,"format_code":null,"source":{"source_id":"src-1","sheet":"Data","address":"D2"}}
]
```

首批矩阵映射示例：

```json
{
  "id":"map-1","source_id":"src-1","schema_version":1,"layout":"matrix_rows",
  "regions":{"elements":{"sheet":"Data","range":"B1:C1"},"conditions":{"sheet":"Data","range":"A2:A3"},"values":{"sheet":"Data","range":"B2:C3"}},
  "metric":{"name":"Distortion","unit":null,"value_kind":"numeric"},
  "condition":{"name":"比例","unit":"%","interpretation":"percent_points"},
  "policies":{"duplicate":"error","missing":"keep","hidden":"include","formula":"cached_only"},
  "transforms":[]
}
```

A01 实施时应覆盖：横纵等价、无表头 records、显式 category_groups、零/空串/missing、公式缓存0/空串/缺失、重复聚合、未知元素、隐藏轴、合并区域、手动大范围、取消、来源变化。32元素×5条件应为5组160条主记录；三个对应表应为15组480条且不吞入 ROUND 辅助区。仅是验收期望，不是本次实测。

A03 实施时应覆盖：非法引用/非有限数/重复ID拒绝且历史不变、相同值无变化、导入一次提交、旧预览拒绝、撤销回保存点、通知失败仍成功、通知重入拒绝、加载失败保留现有项目、仅高亮不切组、切组可撤销、保存重开恢复绑定、批量覆盖不写回。

本批可直接据此实现四个 DTO、A01 转换与预览、A03 命令包装及 selector；不能以本文件代替完整项目 schema 或全部 WorkbookReader/DiagnosticService 端口定义。尚未冻结的端口由 A00 后续补齐，消费方不得擅自扩展这四个已冻结 DTO。
