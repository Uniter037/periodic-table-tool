# GUI 美化与待办列表

## 已完成

- [x] 新增 `ui_theme.py`：浅色/深色调色板、字体/间距 token、`apply_theme()`（clam 主题）
- [x] 左侧控制面板可滚动（Canvas + Scrollbar，Windows/Linux 滚轮）
- [x] 主按钮、卡片、状态栏、表格斑马纹等组件美化
- [x] 窗口标题版本号修正为 v1.3.1
- [x] 新增「视图 → 主题」浅色/深色切换，并持久化到配置
- [x] `make_dist.py` 打包清单加入 `ui_theme.py`
- [x] 新增 `tests/test_theme.py` 并跑通 46 项测试（除一致性测试）

## 待解决

- [ ] **Arial/Helvetica 字体缺失**：Linux 环境无 Arial，matplotlib 回退 DejaVu Sans，日志大量 `Font family 'Arial' not found`，且 CJK 字形缺失。需要增加字体解析与回退机制。
- [ ] **一致性测试附件缺失**：`tests/verify.py` 依赖 `.reasonix/attachments/clipboard-*.py` 原始脚本，当前压缩包未包含，导致 `test_consistency.py` 12 个子测试失败。
- [ ] 高 DPI 适配（Windows 下 `SetProcessDpiAwareness`）。
- [ ] 生成按钮 loading 状态，避免重复点击。
- [ ] 左侧参数区进一步分区与视觉分隔。
- [ ] PyInstaller spec 增加图标/版本资源。
- [ ] 深色模式下部分 matplotlib 预览图背景保持白色，需确认是否需要同步暗色渲染。

## Next Steps

We need to:

1. We need to add a font resolver in `core/styles.py` (or a new `core/fonts.py`) that tries Arial → Helvetica → DejaVu Sans → available CJK fonts, and configure matplotlib font fallback.
2. We need to add a regression test that asserts rendering under Linux does not emit `Font family 'Arial' not found` warnings for the built-in 14 styles.
3. We need to obtain or regenerate the missing `.reasonix/attachments/clipboard-*.py` files, then run and pass `tests/test_consistency.py`.
4. We need to add Windows high-DPI initialization guarded by `sys.platform == "win32"` and `getattr(sys, "frozen", False)` or simply platform check.
5. We need to add a "生成中..." disabled state to the generate button during figure rendering/saving.
6. We need to re-run `pytest --ignore=tests/test_consistency.py` after each change to keep the 46-test baseline green.
7. We need to push the committed changes to GitHub; if network/credentials are missing, produce a `periodic-table-tool-gui-beautify.patch` as the upload artifact.
