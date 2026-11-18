# 桌面工作台 v2 实施接口

父代理负责 ui/workbench_v2.py 与默认启动入口；两个独立写集分别实现应用会话、设置编辑面板。新桌面不导入旧 main、STYLES、scientific、options 或旧 project_codec；旧项目只经显式 migration 加载。

## WorkbenchSession

`application.workbench_session.WorkbenchSession(user_dir=None)`，无Tk依赖。

- `.document` 完整schema2快照（返回独立副本）；`.plot`、`.data` 独立副本；`.path` Path或None；`.revision` 文件指纹或None；`.dirty` bool；`.collection` 返回独立DatasetCollection或提供snapshot即可。
- `patch(plot=None,data=None,replace_data=False)` 事务性修改。plot顶层合并；data合并，None删除；replace_data清空。保持Excel所属组编辑。失败不改历史。
- `apply_preset(payload,include_data=False)` payload为{plot,...可选data}；只替换绘图配置，默认保留数据/Excel关联。
- `undo()/redo()` 返回bool；所有图形、数据、Excel变更进历史。
- `load(path,migrate=False)` 读取schema2；schema1且migrate=False抛MigrationRequired带report；migrate=True转换到未命名工作区，保留.source_path，不覆盖源文件；返回report或None。失败不改变当前状态。
- `save(path=None)` 保存schema2，现有路径检查revision及API锁，另存已存在路径时同样检查已加载文件身份（不允许未经加载覆盖陌生文件）；返回Path，成功更新path/revision/dirty。
- `import_excel(preview,index=0)` 使用ExcelImportService.preview结果导入所有组并选中index；`select_dataset(id)` 切换；`batch_items(ids=None)` 返回[(metadata,data)]，最多100同指标组，保留编辑。
- `auto_range()` 根据include_in_range过滤有效热力数据，常量组安全扩展范围，保留线性/中心分段类型，更新norm。无数据或非数值类型抛ValueError。
- `save_preset(name,include_data=False)/load_preset(name,include_data=False)/list_presets()/delete_preset(name)` 使用独立v2预设目录，不覆盖旧v1预设；名称由已有PresetStore校验。
- `save_draft()/recover_draft()/clear_draft()` 独立v2草稿，恢复为未命名且dirty，不覆盖源项目。

可以复用现有 APIv2 validate_document/_patch/_save 或持久化原语，但不能把Tk、控件文本或模式ID放入项目。所有状态变更必须验证有效。未修改数据的样式操作不得把Excel组解除关联。

## PlotSettingsPanel

`ui.plot_settings_v2.PlotSettingsPanel(master,on_change,on_error=None)`。

- `set_plot(plot)` 载入规范配置且不触发回调；`get_plot()` 返回当前完整有效PlotSpec dict（无效抛ValueError）。
- on_change(patch:dict) 仅提交合法的已修改顶层字段，on_error(message:str)展示错误；不能因无效字段触发reset或静默回退。防抖后自动提交；配色及范围等组合字段以一次patch提交。
- 中文图形化字段、可滚动分组、设置搜索，kind/layout/cmap/norm/format/font/title/字号/显隐/色条及画幅/DPI等常用选项直接可编辑，不能只给JSON文本框。
- 色条表格支持增加/删除/修改、逐行显示隐藏及字号；保留隐藏行和全局show_cbar_labels。可通过独立dialog处理复杂字段。
- 自定义颜色节点、精确margins/cbar_box、边框、透明、图形覆盖字段均需可编辑。JSON高级编辑器可作为复杂配置的补充，但不能是常用操作唯一入口。
- 不直接读文件、改会话或渲染；父容器接收patch后负责会话、撤销及预览。

窗口布局、DPI/缩放、数据表、图形标注、后台worker与预设按钮由父代理实现，不在设置面板代理写集。
