# v1.9.0 验证记录

日期：2026-11-13。平台：Windows x64，CPython 3.14.2。

- 全量 `python -m pytest -q`：777 passed，13 subtests passed，64 warnings；退出码 0。保留现有依赖警告。
- 使用 `build_exe.py` 固定依赖构建单文件 EXE，退出码 0。
- `verify_exe.py` 在独立目录运行实际 EXE：启动、预览、PNG/SVG/PDF 导出通过；6 次 Agent 调用验证创建、修改、检查、过期写入拒绝和导出。
- 新功能专项：10 次实际 EXE 调用，通过 describe、无状态 render、标注诊断开关、合成 Excel 导入、两组 batch_export、固定色标、文件哈希与 PNG/SVG 结构检查。项目和工作簿未修改。
- SVG 几何对比：固定画幅下，保留颜色条占位时显示/隐藏颜色条的主图单元格路径和文字变换一致；关闭占位时布局会变化。

EXE SHA-256：`f9e001eaccff030951ea144dc049f813052f3a13ac7c51062b0bac416b0f13d0`。

排版诊断是文字包围盒提示，不自动修改字号或位置。上述验收不等同于所有 Windows 版本、字体环境及任意用户输入均已覆盖。包内数据示例为合成数据；本地科研数据和测试输出不作为发行附件。
