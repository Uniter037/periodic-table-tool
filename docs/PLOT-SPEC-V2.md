# PlotSpec v2 实施契约

本文件冻结本轮代理共享接口，业务语义优先于底层库。领域层不得导入 core、Tk 或 Matplotlib。

`domain.plot_spec.PlotSpec.from_dict(mapping)` 验证、补默认值并保留输入隔离；未知键拒绝。`to_dict()` 返回独立 JSON 字典。`PlotSpecError(ValueError)` 含 `path`。配置不含 data、输出路径、脚本 ID、兼容开关。

本轮使用扁平但有类型的配置，避免为每个控件再嵌套一层 DTO。字段：

| 字段 | 默认与约束 |
| --- | --- |
| kind | heatmap / labels，默认 heatmap |
| layout | expanded / compact，默认 expanded |
| cmap | coolwarm；或 [custom, 颜色列表/位置颜色节点]；名称真实性由后端校验；不允许冒号模块路径 |
| norm | [twoslope,-1,0,1] 或 [normalize,min,max]；有限且严格递增 |
| fmt | raw/g/percent2/2f/3f/4f/scientific，默认 3f |
| rounding | half_up / python，默认 half_up |
| font | Arial，非空字符串 |
| figsize | [10,5]，英寸；宽 2~40、高 1~40 |
| dpi | 100，有限数 36~1200 |
| title | 空字符串 |
| show_cbar, show_cbar_labels | true |
| preserve_cbar_space | false |
| check_label_overlap | true |
| bbox_tight, transparent | false |
| show_symbol, show_number, show_value | true |
| symbol_fs, number_fs, value_fs | 9,6,6，有限正数 |
| value_dx, value_dy | 0，-2~2 |
| label_wrap | 0，整数 0~200 |
| unit | 空字符串 |
| edge | null 或 [线宽0~20,颜色] |
| empty, bg, label_color | #f0f0f0,#f0f0f0,auto；label_color=auto 按底色选择对比文字，显式颜色始终保留，文本预设可用灰色 |
| label_fs, label_dy | 8,0.12，字号正数、偏移有限 |
| num_x, num_ha | 0.2,center；位置有限，left/center/right |
| highlight_bg, highlight_fg, plain_bg, plain_fg | null,null,null,null；非null为颜色 |
| margins | null 或 [left,bottom,right,top]，0<=left<right<=1 等 |
| cbar_box | null 或 [x,y,w,h]，完整位于Figure内且宽高>0 |
| cbar | null 或 {ticks,labels,visible,fontsize}；有限不重复刻度，保留隐藏行，默认 visible全true、fontsize8 |
| cbar_orientation, cbar_location | vertical,auto；vertical/horizontal，auto/left/right/top/bottom，组合相容 |
| cbar_label | 空字符串 |
| cbar_fraction,cbar_pad,cbar_shrink | .046,.04,1；.005~.5,0~.5,.05~1 |
| element_overrides | {}；有效元素，show_value/show_color/include_in_range bool，value_dx/value_dy有限数 |

颜色允许非空名称/十六进制字符串或RGB(A)数值数组；后端做Matplotlib色名验证，领域层不携带Matplotlib色表。数字类型不得接受bool、NaN或Infinity。序列输出统一JSON list。

`domain.plot_layout.build_layout(layout)` 纯几何API由渲染代理定义内部DTO；expanded 包含118格，compact 附带隐藏元素清单及正确系列说明，布局不注入数值。

`infrastructure.rendering.renderer.render_plot(spec: PlotSpec, data: dict)` 返回Matplotlib Figure，使用spec的title/show_cbar/figsize。不导入 core.styles、core.options、core.scientific、core.ptable。允许复用 core.fonts、core.elements_data（后续移动）、core.dataio 的数据解析（不得读STYLES）；图元继续提供 _ptable_element/_ptable_role/_ptable_cell。颜色与文字模块独立实现，不保留 custom/corrected/text_always 分支。

`application.project_migrations.migrate_document(document)` 返回 {document,report}，document schema=2、current={plot:spec_dict,data:原数据,...其余持久化信息}、styles={旧状态名:同结构}，保留顶层其余字段。report含 source_schema,target_schema,changed_fields,warnings,unsupported_fields。schema2重复迁移结果不变。迁移器是唯一可以引用旧style resolver的新增模块；原始payload保存在 migration_source 中用于审计，渲染不得读取它。

每个旧payload通过真实生效配置展开，再白名单构造spec。旧 rounding legacy 映射python；旧 layout classic/reconstructed映射expanded/compact。旧cmap预览状态无法转为周期表，明确报告不支持并阻止迁移，不静默丢弃。旧cbar_override的隐藏行、show_cbar_labels必须单独保留。

应用服务负责迁移后的文件原子写入、防覆盖命名、数据组、诊断和接口；代理不得修改其工作集外文件。
