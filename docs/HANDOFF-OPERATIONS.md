# 运维交接附录：构建、验收、发行与恢复

历史核对基线：2026-11-08、v1.8.0。当前发行操作目标：v1.9.0（2026-11-13 文档更新）。本附录描述脚本与代码及供接手人执行的操作步骤；不替代主架构文档。

## v1.9.0 运维增量

本版新增 Agent `render`、`batch_export`、`describe` 参数选项/操作元数据与冲突恢复详情；标注诊断默认开启（`display.check_label_overlap=true`），颜色条占位默认关闭（`display.preserve_cbar_space=false`），对照图使用固定画幅。契约见 [Agent 高效绘图流程](AGENT-WORKFLOWS.md)。发行验收还需核查新 action、批量结果与逐组 `layout_issues`、冲突详情及两个显示开关；既有六次 Agent 验收不能单独证明这些新增能力。

下文保留 v1.8.0 历史证据，当前组装与校验命令使用 v1.9.0。v1.9.0 EXE 已完成构建与验收，最新结果见 [本版验证记录](RELEASE-v1.9.0.md)。下文“本文编写过程中”的未执行声明仅指最初交接文档编写，不代表本版发行验证状态。

## 1. 证据范围与当前边界

已静态核对 `build_exe.py`、`make_dist.py`、`verify_exe.py`、`requirements.txt`、`pyproject.toml`、`main.py`、`core/document.py`、`core/jobs.py`、`infrastructure/diagnostics/`，以及打包、EXE 校验、诊断和草稿相关测试。本文编写过程中没有执行测试、重新构建 EXE、生成发行归档或发布。

**717 项测试通过是交接上下文提供的既有基线，本次没有重新运行，也没有将其作为当前工作树的通过证明。** 后续验收须保留实际命令、解释器与依赖版本、退出码、通过/跳过/失败数量和对应提交标识；测试数量变化时不能仅凭数量判定回归。

当前 `.ptproj` 顶层仍为 `schema: 1`，包含 `current`、`styles` 等字段；Excel 数据组由现有扩展承载。`core/document.py` 明确拒绝非 1 项目格式。设计目录中的项目 schema=2、输出 journal/manifest 恢复协议、全套结构化日志架构不能当作已落地功能。日志事件的 `schema_version: 1`、Excel 映射版本和 Agent 的 `api_version: 1` 是不同协议。

## 2. 源码环境与测试命令

以下均在 Windows PowerShell、仓库根目录执行。源码运行要求 Python 3.10+ 且有 Tkinter；正式 EXE 构建另有更严格要求。

```powershell
Set-Location 'C:/path/to/periodic-table-tool' # 替换为实际 checkout 路径
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install pytest setuptools wheel
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m tkinter
.\.venv\Scripts\python.exe main.py
```

`python -m tkinter` 打开测试窗口，关闭后继续。运行依赖为 Matplotlib>=3.6、NumPy>=1.24、Pillow>=9.2、resvg_py==0.5.0；`pyproject.toml` 与 requirements 一致。前三者是下限约束，普通开发安装不是固定依赖快照。pytest 是开发依赖，需要另装；setuptools/wheel 用于测试中的源码归档 wheel 构建。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# 按问题范围复查；不能替代发行前全量测试
.\.venv\Scripts\python.exe -m pytest -q tests/test_dist.py tests/test_exe_verification.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_diagnostics.py tests/test_diagnostics_gui.py tests/test_project_workflow.py
```

pytest 配置只指定 `testpaths = ["tests"]`。`tests/conftest.py` 在导入 main 前将 `PTT_USER_DIR` 指向临时目录，共享一个真实 Tk 应用实例，并为各测试恢复文档和输出路径；不应在无可用桌面的环境里把 GUI 失败解释为业务通过。绘图使用 Agg，但界面测试仍需 Tk。`test_dist.py` 会实际生成归档、用 `pip wheel --no-deps --no-build-isolation` 构建并检查隔离导入；固定原脚本基准共 12 份，位于 `tests/fixtures/originals/`。

## 3. EXE 固定构建流程

必须用 **Windows CPython 3.14.2 x64，含 Tkinter** 运行，脚本会严格检查平台、实现、补丁版本与机器架构。

```powershell
# 先确认当前 python 确实是 3.14.2 x64；必要时改为该解释器的绝对路径
python -c "import sys, platform, tkinter; print(sys.executable); print(sys.version); print(platform.machine())"
python build_exe.py
if ($LASTEXITCODE -ne 0) { throw 'EXE 构建失败，停止发行' }
```

脚本创建/使用 `.venv-build-exe`，通过网络安装全部精确版本，并限制 `--only-binary=:all:`，随后执行 pip check 和 PyInstaller。没有可用 wheel、网络故障或版本不符会中止；不能私自去掉版本限制后仍称为同一构建流程。

| 项目 | 实际行为 |
| --- | --- |
| 工具链 | pip 25.3、setuptools 83.0.0、PyInstaller 6.21.0、hooks-contrib 2026.6；完整固定清单以脚本 `REQUIREMENTS` 为准 |
| 主要绘图依赖 | matplotlib 3.11.1、numpy 2.5.1、pillow 12.3.0、resvg_py 0.5.0；其余依赖同样固定 |
| 参数 | `--onefile --windowed --noupx --clean --noconfirm`，入口 main.py |
| 收集 | core/ui/application/infrastructure/domain 子模块；TkAgg/Agg/SVG/PDF、PIL.ImageTk 与 PIL._imagingtk 隐藏导入；resvg_py 全收集 |
| 构建目录 | `build/exe`、`build` 中的 spec、`build/pyinstaller-cache` |
| 输出 | `dist/PeriodicTableTool.exe` |
| 子进程环境 | `PYTHONHASHSEED=0`、`SOURCE_DATE_EPOCH=1577836800`、专用 `PYINSTALLER_CONFIG_DIR` |

脚本不上传、不签名、不创建 Windows ZIP，也不生成 SHA256SUMS。固定工具链有助于复现流程，**不保证 PE 字节逐次相同**。虚拟环境创建不等于清空已有环境；怀疑环境污染时应保留证据后在新工作副本构建。

## 4. 冻结程序验收

```powershell
.\.venv\Scripts\python.exe verify_exe.py dist/PeriodicTableTool.exe --timeout 180 --report output/exe-acceptance.json
if ($LASTEXITCODE -ne 0) { throw '冻结程序验收失败，停止发行' }
```

验证器自身需要 Pillow（源码依赖已包含），不是零依赖验证程序。它把 EXE 复制到 `ptt-exe-acceptance-*` 全新临时目录，设置 `PTT_SMOKE=1`、独立 `PTT_SMOKE_EXPORT_DIR` 和 `PTT_USER_DIR`，启动真实程序并等待退出；Windows 隐藏窗口。超时后用 taskkill 终止进程树。

验收检查：

- 本轮 `smoke_progress.txt` 必须包含 app_created、preview:passed、三种 export、smoke:passed、after_mainloop，且不得有 smoke:failed。
- 输出目录必须每种格式恰好一份且非空；PNG 可解码、画幅有效且非纯色；SVG 根元素正确；PDF 有头尾标记。它不进行全文 PDF 语义或像素金图比对。
- 同一 EXE 的无 Tk Agent 接口完成 describe/create/update/过期 update/inspect/export 共六次请求，确认过期 revision 被拒绝、修改保留、PNG/SVG/PDF 均生成。
- 成功 JSON 报告包含 EXE SHA-256、总耗时、图片大小/哈希、PNG 像素和 Agent 结果。`--timeout` 是 GUI 子进程等待上限，Agent 各次调用使用 `min(timeout, 60)`，不是整个脚本的统一总时限。

临时目录在退出时清理，不能指望失败后还能找到其中日志；报告仅在全部成功后写入。历史报告也可能仍在，因此失败时不得沿用旧报告。必要时另行设置三个 PTT 环境变量，在人工保留的独立目录运行 EXE，复现并保存本轮标记与输出；勿把已有 `dist/smoke_progress.txt` 当作新验收证据。

自动验证没有证明目标电脑无 Python、离线、非管理员及中文路径均可用。发行前仍需在对应干净 Windows 环境解压 Windows ZIP，实测启动、Excel 导入、预览、项目保存/重开、三格式导出、样图显示及草稿恢复；记录实际字体差异。

## 5. 本地发行组装：四件套与校验

先完成全量测试、EXE 构建和验收，再生成源码包。以下是人工组装步骤，**不是现有 make_dist.py 的自动能力**。版本应同时核对 main 窗口标题、README、pyproject.toml、make_dist.VERSION；`test_version_consistent` 中的版本断言也须与本次发行一致。

```powershell
.\.venv\Scripts\python.exe make_dist.py
if ($LASTEXITCODE -ne 0) { throw '源码包生成失败' }

$releaseVersion = '1.9.0'
$windowsZip = Join-Path (Get-Location) "dist/periodic-table-tool-v$releaseVersion-windows.zip"
if (Test-Path -LiteralPath $windowsZip) { throw 'Windows ZIP 已存在，请先保留旧产物并选择干净发行目录' }
Compress-Archive -LiteralPath '.\dist\PeriodicTableTool.exe', '.\README.md', '.\docs', '.\examples' -DestinationPath $windowsZip

$releaseFiles = @('PeriodicTableTool.exe', "periodic-table-tool-v$releaseVersion-windows.zip", "periodic-table-tool-v$releaseVersion.zip")
$checksumPath = Join-Path (Get-Location) "dist/SHA256SUMS-v$releaseVersion.txt"
if (Test-Path -LiteralPath $checksumPath) { throw '校验清单已存在，请先保留旧清单再重新生成' }
$checksumLines = foreach ($releaseName in $releaseFiles) {
    $releaseHash = (Get-FileHash -LiteralPath (Join-Path '.\dist' $releaseName) -Algorithm SHA256).Hash.ToLowerInvariant()
    "$releaseHash  $releaseName"
}
$checksumLines | Set-Content -LiteralPath $checksumPath -Encoding ascii
```

Windows ZIP 放 EXE、README、文档与示例，保留 README 的相对链接结构；压缩前检查 docs/examples 中只有允许交付的文件。不要将整个 dist 压入而带入历史发行、预设、用户输出和冒烟日志。若仓库已有同版本 ZIP/清单，上述防覆盖检查会要求先人工保留旧产物；EXE 构建和 make_dist 则可能覆盖同名输出，应在执行整个流程前留存上一版。

`make_dist.py` 在版本代码同步到 v1.9.0 后应生成 `dist/periodic-table-tool-v1.9.0.zip`，内部根目录为 `periodic-table-tool/`：固定入口/构建脚本、五个运行包及 tests 下的 Python、全部 tests/fixtures 与 docs/workbench 文件、docs 根目录 Markdown、examples 中 txt/json/csv/tsv 白名单。本次交接补齐了 docs 根目录 Markdown 的收录，因此后续新构建的源码包包含两份交接文档；已发布的 v1.8.0 附件不会自动改变。它不打包整个仓库、不包含 dist、虚拟环境、缓存、用户目录。示例白名单不替代内容审查，放入 examples/fixtures 的敏感内容仍可能进入包。

源码 ZIP 对路径排序、时间戳（2020-01-01）、权限等做固定处理；测试检查同输入两次归档字节一致。Windows Compress-Archive 步骤没有相同的确定性承诺。校验和必须针对最终字节生成，修改 EXE 或重压 ZIP 后必须重算。

校验已有清单时，在仓库根目录执行；不能只目视文件存在：

```powershell
Get-Content -LiteralPath '.\dist\SHA256SUMS-v1.9.0.txt' | ForEach-Object {
    $checksumParts = $_ -split '\s+', 2
    if ($checksumParts.Count -ne 2) { throw '校验行格式无效' }
    $actualHash = (Get-FileHash -LiteralPath (Join-Path '.\dist' $checksumParts[1]) -Algorithm SHA256).Hash
    if ($actualHash -ne $checksumParts[0]) { throw "校验失败：$($checksumParts[1])" }
}
```

最终核对三件产物、版本化 SHA256SUMS、发行说明与验收报告的对应关系；在全新解压目录复查 ZIP 内容。仓库残留的旧哈希不是当前 EXE 的认证。本任务仅编写附录，没有提交、上传或发布。

## 6. 目录、配置与环境变量

| 位置/变量 | 实际用途与运维注意 |
| --- | --- |
| 默认用户根 | `Path.home() / '.periodic-table-tool'`，不是 LOCALAPPDATA/APPDATA |
| `PTT_USER_DIR` | 替换整个用户根；启动前设置，建议绝对路径。显式设置时跳过旧文件迁移；不是输出图片目录开关 |
| `settings.json` | 用户根下的 UI 配置，含 diagnostics.enabled/level；日志开关与级别即时应用并保存 |
| `presets/` | 用户根下的预设；未设 PTT_USER_DIR 时，只复制缺失的旧预设，不覆盖已有用户预设 |
| `draft.ptproj` | 用户根下单份自动草稿，含实际项目数据；不是日志 |
| `logs/<session_id>/events-000000000001.jsonl` | 按实例会话、递增序号保存诊断事件 |
| 默认图片输出 | `PROJECT_ROOT/output`；源码为仓库旁，冻结版为 EXE 旁，可能受目录权限影响；用户配置/项目可改变输出位置 |
| 旧配置迁移 | 未显式设 PTT_USER_DIR 时，从 `~/.periodic-table-tool.json` 复制到缺失的 settings.json，从 PROJECT_ROOT/presets 复制缺失预设；不是搬移/删除旧文件 |
| `PTT_SMOKE=1` | 打包测试专用：隐藏窗口、执行冒烟流程，并抑制正常草稿写入/恢复提示；日常运行不要遗留 |
| `PTT_SMOKE_EXPORT_DIR` | 冒烟图片目录，配合 PTT_SMOKE 使用；标记写到 `sys.executable` 同目录，源码运行时不一定在仓库 |
| 构建环境变量 | HASHSEED/EPOCH/PYINSTALLER_CONFIG_DIR 由 build_exe 传给子进程，不是用户运行配置 |

隔离排查示例：

```powershell
$env:PTT_USER_DIR = Join-Path $env:TEMP ('ptable-support-' + [guid]::NewGuid().ToString('N'))
Remove-Item Env:PTT_SMOKE -ErrorAction SilentlyContinue
Remove-Item Env:PTT_SMOKE_EXPORT_DIR -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe main.py
# 排查结束，关闭应用后恢复当前 PowerShell 会话的默认用户目录选择
Remove-Item Env:PTT_USER_DIR -ErrorAction SilentlyContinue
```

若此前已有 PTT_USER_DIR，应先记录并恢复原值，不要直接清掉。隔离目录自身仍须保留或人工清理；关闭环境变量不删除它。

## 7. 日志、诊断包与隐私

实际 GUI 入口是顶层「日志与排错」，包含记录开关、WARNING/INFO/DEBUG、查看本次日志、临时详细排错（30分钟）、结束临时排错、导出本次诊断包。查看器在 main.py 内，只显示本次最多 300 条，手动刷新；不存在已实现的 ui/diagnostics 模块、跨会话浏览器或 GUI 清空历史按钮。

服务使用同步写入与 RLock，**不是**设计中的 QueueListener/worker 队列。默认开启 INFO，单文件 2 MiB、单会话总量 20 MiB、保留 7 天，单事件不超过 32 KiB。轮转/清理只遍历当前实例会话目录，不能据此承诺全部历史会话的磁盘总量永远小于 20 MiB。服务有筛选/游标查询和 clear_history API，后者只删本会话匹配命名的事件文件，不删其他实例或任意 journal 文件。

关闭开关停止新诊断持久化；临时 DEBUG 即使原先关闭也会暂时启用，定时到期/主动结束恢复基础设置，手动改配置结束临时模式；临时状态不持久化。写盘错误置 `write_failed` 并停止此实例后续写入，不记录原始底层异常、不自动重试。GUI 尚未提供完整磁盘失败告警和启动期/线程/worker 全链路异常捕获，缺日志不能当作没有故障。

隐私实现要点：

- safe_text 对路径、用户名及常见秘密/单元格/标注字段形式脱敏，文本截断至 2048 字符；不是任意正文内容的语义识别器，调用方仍应使用静态消息。
- details 仅允许计数类字段；异常只保存类型和最多 100 帧的函数/行号，文件替换为 `<SOURCE>`，不采集异常正文或局部变量。
- ZIP 导出重新做字段白名单与脱敏，只有 `events.jsonl`、`metadata.json`，不自动附加 Excel、项目、元素数据、剪贴板或环境变量全集，不自动上传。
- metadata 包含操作系统、Python、Matplotlib/NumPy/Pillow 版本、设置、会话和事件数；应用版本来自包元数据，在未安装包或冻结环境可能为 null，不是可靠构建指纹，也不含完整字体、显示缩放与所有依赖清单。
- 导出先写临时 ZIP，再用硬链接发布为 diagnostics-会话.zip，已存在时加序号，不覆盖。目标文件系统不支持硬链接时可失败，应改选支持的本地目录；不承诺所有网络盘可用。

对外发送前人工复查诊断包。验收报告、Agent 请求/响应、项目、草稿与 GUI 错误对话框不属于同一日志脱敏通道，可能包含绝对路径和科研数据。不得为了排错直接收集整个用户目录。

## 8. 故障恢复与接手处理

1. **启动/构建失败**：记录解释器实际路径、版本与位数，确认 Tk、pip check 与固定 wheel 下载；windowed EXE 无控制台不等于启动成功。用隔离 PTT_USER_DIR 复现，区分用户配置问题与程序问题。日志服务建立前的导入失败不保证有诊断记录。
2. **配置损坏或界面异常**：关闭所有实例，先备份用户根；在独立用户根启动对照。需要重置时只对备份后的 settings.json 做定向处理，不删除整个用户根。草稿、预设和项目各自独立保留。
3. **异常退出/草稿恢复**：状态变更后约 800 ms 防抖写草稿，快照与已保存状态相同则移除；待恢复时不覆盖旧草稿。启动检测到 draft.ptproj 后询问恢复，选择拒绝会删除草稿，故排查前先备份。恢复后立即另存正式项目。schema 不符/损坏会在状态栏报错，不能声称自动修复。该目录只有一份草稿，多实例并非独立草稿隔离。
4. **项目保存失败**：write_document 在目标同目录临时写入、flush/fsync 后 os.replace；检查父目录、权限、磁盘空间并保留原项目。原子替换不能替代备份，也不提供完整跨文件事务恢复。
5. **预览卡住/worker 异常**：先取消任务、降低画幅/DPI，用小数据复现；保留本轮输入条件和实际已导出文件。RenderJob 使用 ptable-render-* 临时目录和独立 worker，取消会清理未发布结果并可重用；不能把普通运行时清理描述为崩溃后持久恢复 journal。
6. **输出失败/部分文件存在**：核对用户选定目录的权限、空间和文件内容；现有图片命名避免覆盖，但没有已实现的 journal/manifest 跨崩溃核对协议。重试前检查哪些图片实际存在并保存证据，不根据缺少日志认定没有输出。
7. **Agent revision 冲突**：先 inspect 取得新的文件字节 SHA-256 revision，重新评估改动再 update；不盲目重试旧请求。Agent 写入锁不覆盖 GUI，编辑同一项目时先保存并关闭 GUI，完成后重新打开。请求/响应文件使用独立路径，并同时检查退出码和 JSON ok。
8. **日志写盘失败/空间增长**：优先恢复目录权限或磁盘空间，再重启创建新服务实例。跨会话清理须关闭相关实例，核实实际 logs 根目录与备份后定向处理；不要连带移除 draft.ptproj、presets、正式项目或图片。关闭日志也不会关闭草稿或撤销图片。

接手记录至少包含：代码/产物版本与 EXE 哈希、运行环境、复现步骤、是否隔离用户根、本轮实际测试结果、验收报告与对应文件、已知限制，以及用户数据是否已备份。不要把设计验收项、历史 717 基线或 dist 中的遗留文件写成这次已验证通过的结论。
