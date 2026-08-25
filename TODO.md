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

- [x] **Arial/Helvetica 字体缺失**：已新增 `core/fonts.py`，Arial/Helvetica 缺失时回退 DejaVu Sans；CJK 文本自动使用微软雅黑（若可用）。
- [ ] **一致性测试附件缺失**：`tests/verify.py` 依赖 `.reasonix/attachments/clipboard-*.py` 原始脚本，当前压缩包未包含，导致 `test_consistency.py` 12 个子测试失败。
- [x] 高 DPI 适配：已在 `main()` 中启用 `SetProcessDpiAwareness`。
- [x] 生成按钮 loading 状态：`generate()` 中禁用按钮并显示「生成中...」。
- [ ] 左侧参数区进一步分区与视觉分隔。
- [ ] PyInstaller spec 增加图标/版本资源。
- [ ] 深色模式下部分 matplotlib 预览图背景保持白色，需确认是否需要同步暗色渲染。

## Next Steps

We need to:

1. We need to keep the font-fix regression green: `pytest --ignore=tests/test_consistency.py` now has **51 passed**.
2. We need to obtain or regenerate the missing `.reasonix/attachments/clipboard-*.py` files, then run and pass `tests/test_consistency.py`.
3. We need to re-run `pytest --ignore=tests/test_consistency.py` after each change to keep the baseline green.
4. We need to push each completed step to GitHub.
