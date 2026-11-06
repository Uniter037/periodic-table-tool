# M0 基线验证

2026-11-05（Asia/Shanghai），14 自然日交付计划 D1 首轮验证。计划交付窗口为 11 月 5 日至 11 月 18 日。

## Git 基线

- `main` HEAD 为 `340271e6adb25aeda3770a317e9b98bb277d13c9`（`feat: add reliable plotting projects and background export in v1.6.0`）。
- HEAD 与本地 `origin/main` 跟踪引用一致，领先 0、落后 0。未刷新远端引用。
- 开始时工作树已有 `README.md` 修改和未跟踪的 `docs/workbench/` 文档。测试结束后状态中另出现未跟踪的 `docs/workbench/EXECUTION.md`。本次验证仅交付此报告和测试日志，未修改程序、测试或依赖。

## 环境与执行

- Windows x64（NT 10.0.26200.0），默认 CPython 3.14.2 x64（`C:\Users\Uniter\AppData\Local\Programs\Python\Python314\python.exe`）。Tcl/Tk 8.6.15，Tk 根窗口探测成功。
- pytest 9.1.1、Matplotlib 3.11.1、NumPy 2.5.1、Pillow 12.3.0、pip 25.3、setuptools 83.0.0。默认环境缺少独立的 `wheel` 包和 `openpyxl`，均未阻断本次测试。
- 已有项目虚拟环境 `.venv-build-exe` 使用 CPython 3.14.2，含 Matplotlib、NumPy、Pillow，缺少 pytest。本次使用默认解释器。
- 在仓库根目录运行 `python -B -m pytest -p no:cacheprovider -ra`，未筛选用例。禁用字节码和 pytest 缓存，pip 禁用索引、缓存和版本检查。打包测试在 pytest 临时目录构建并解包 wheel，未向环境安装或升级包。

## 结果

| 指标 | 实测 |
| --- | ---: |
| 收集 | 315 |
| 通过 | 315 |
| 失败 | 0 |
| 错误 | 0 |
| 跳过或已收集但未运行 | 0 |
| 警告 | 20 |
| pytest 退出码 | 0 |
| pytest 报告耗时 | 117.99 秒 |
| 外部计时（含进程启动和日志写入） | 121.32 秒 |

现有 pytest 基线通过，无阻断项。20 条警告包括 Matplotlib `set_under` 待弃用提示和坐标轴容差运行时警告。

本轮未执行独立 EXE 构建、实际 EXE 冒烟或真实 Excel 验收。这些项目在本次 pytest 范围之外。未读取用户 Excel。

原始日志见 [m0-baseline-pytest.log](../../output/m0-baseline-pytest.log)，`output/` 由 Git 忽略。
