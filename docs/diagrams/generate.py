"""Regenerate editable handoff SVGs and PNG previews; run from repository root."""
from pathlib import Path
from html import escape
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from core.reference_image import load_reference_image
OUT=Path(__file__).parent

def text(x,y,s,size=22,color='#334155',weight=400):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}">{escape(s)}</text>'
def card(x,y,w,h,title,lines,color='#2563eb'):
    s=f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="white" stroke="#dbe3ee"/><rect x="{x}" y="{y+18}" width="5" height="28" rx="2" fill="{color}"/>'
    s+=text(x+22,y+43,title,25,color,700)
    for i,line in enumerate(lines): s+=text(x+22,y+82+i*31,line,20)
    return s
def arrow(x1,y1,x2,y2):
    return f'<path d="M{x1} {y1} L{x2} {y2}" stroke="#94a3b8" stroke-width="3" fill="none" marker-end="url(#arrow)"/>'
def save(name,title,subtitle,body,note):
    svg='<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="900" viewBox="0 0 1440 900"><defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0 0 L0 6 L8 3 Z" fill="#94a3b8"/></marker><linearGradient id="heat" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#2c4b75"/><stop offset="0.5" stop-color="white"/><stop offset="1" stop-color="#91221c"/></linearGradient></defs><rect width="1440" height="900" fill="#f1f5f9"/><g font-family="Microsoft YaHei,Arial,sans-serif">'
    svg+=text(60,75,title,38,'#0f172a',700)+text(60,117,subtitle,21)+body
    svg+=text(60,842,note,19)+text(60,878,'周期表绘图工作台 · v1.8.0 基线 · 说明图 / 2026-11-12',16,'#64748b')+'</g></svg>'
    path=OUT/(name+'.svg'); path.write_text(svg,encoding='utf-8')
    load_reference_image(path).save(OUT/(name+'.png'))

body=card(60,160,410,165,'桌面 GUI',['main.App / Tkinter','控件、编辑、撤销、任务编排'])
body+=card(970,160,410,165,'Agent / 自动化',['JSON API v1 · CLI / EXE','项目修改、Excel 导入、图片导出'])
body+=card(500,370,440,165,'共享解析与绘图规则',['project_codec / core.options','scientific / styles / ptable'],'#0f766e')
body+=arrow(265,325,500,410)+arrow(1175,325,940,410)
body+=card(60,590,410,170,'数据与持久化',['ExcelImportService / DatasetCollection','domain DTO / XLSX Reader','schema=1 项目 / 预设'])
body+=card(500,590,440,170,'绘图执行',['GUI：RenderJob → spawn 子进程','Agent：当前进程直接 Agg 渲染','共同使用 render_table'],'#0f766e')
body+=card(970,590,410,170,'图片与排错',['PNG / SVG / PDF 自动命名','日志开关、临时 DEBUG、诊断包','参考图加载与人工对照'])
body+=arrow(720,535,720,590)+arrow(470,675,500,675)+arrow(940,675,970,675)
save('01-architecture','01 / 系统架构','两个入口，共享科学规则；GUI 状态仍主要由 main.App 管理。',body,'边界：Agent 操作项目文件，不实时控制 GUI；ProjectStore 尚未替代 App 的 History。')

body=''
for x,title,lines in [(60,'① 输入与来源',['文本 / 手工 / Excel','保留原始值、公式缓存和来源']), (510,'② 校验与当前数据',['类型、元素、重复值、有限数','Excel 来源快照 + 每组编辑缓冲']), (960,'③ 参数与图形规则',['布局、norm、cmap、显示精度','元素覆盖、颜色条、物理尺寸'])]:
    body+=card(x,190,420,180,title,lines)
body+=arrow(480,280,510,280)+arrow(930,280,960,280)
body+=arrow(1170,370,1170,450)
body+=card(960,450,420,190,'④ 绘制 Figure',['共享 render_table 内核','颜色 = 原始值 → norm → cmap','舍入仅影响显示'],'#0f766e')
body+=card(510,450,420,190,'⑤ 预览 / 正式导出',['预览：低分辨率 + 命中区域','导出：指定画幅、DPI、裁切','UI 选中框不进入成图'],'#0f766e')
body+=card(60,450,420,190,'⑥ 文件与可恢复项目',['图片自动命名，避免覆盖','项目保存参数、数据与编辑状态','切组、撤销不删除已导出图片'],'#0f766e')
body+=arrow(960,545,930,545)+arrow(510,545,480,545)
body+=card(60,680,1320,110,'关键不变量',['隐藏 ≠ 删除原值；界面缩放 ≠ 改变画幅；颜色条标签 ≠ 数值归一化。'],'#b45309')
save('02-data-flow','02 / 从输入到成图','先保证数据语义，再解析图形参数，最后检查实际图片。',body,'Excel 公式只读取已保存缓存；当前没有自动重算公式或自动源文件同步。')

body=''
steps=[('1 · describe',['查询字段、默认值','和可用样式']),('2 · inspect',['读取项目','取得文件 SHA-256']),('3 · validate',['内存试算 patch','不写项目文件']),('4 · update',['携带','expected_revision']),('5 · export',['使用更新后的','revision'])]
for i,(title,line) in enumerate(steps):
    x=60+i*268; body+=card(x,205,248,155,title,line, '#2563eb')
    if i<4:body+=arrow(x+248,282,x+268,282)
body+=card(60,430,640,230,'成功路径',['validate 返回 base_revision','update 返回新的 revision','export 返回路径、字节数与 SHA-256','新项目先 create；图片支持 PNG / SVG / PDF'],'#0f766e')
body+=card(740,430,640,230,'冲突与失败路径',['REVISION_CONFLICT → 再次 inspect','重新评估 patch，不能盲目覆盖','原地 API 更新使用协作锁与原子替换','GUI 未参与 API 锁，建议关闭或另存后重开'],'#b45309')
body+=text(60,730,'CLI：python -m application.agent_api --request request.json --response response.json',23,'#0f172a')
body+=text(60,772,'调用方同时检查：进程退出码 + 响应文件存在 + JSON ok 字段。',23)
save('03-agent-workflow','03 / Agent 项目编辑协议','本地 JSON 单请求接口；文件 revision 与 GUI 内存状态不是同一概念。',body,'validate 不会保存修改；同一项目被其他工具修改后，旧 revision 必须失效。')

body=card(60,170,640,200,'① 数据与显示元素',['选定工作表、条件和数值区域','记录原始值、显示舍入与来源 hash','分别设置数值隐藏、着色隐藏、参与自动范围'])
body+=card(740,170,640,200,'② 几何与文字',['对齐布局、物理画幅、格距、字体与字号','margins：left / bottom / right / top','cbar_box：x / y / width / height'])
body+=card(60,410,640,285,'③ 样板颜色条：Dis1.39',['深蓝 → 白 → 深红；双斜率归一化','中心值位于色条中点，不能只改标签'],'#0f766e')
body+='<rect x="95" y="555" width="560" height="46" rx="4" fill="url(#heat)" stroke="#94a3b8"/>'
body+=text(95,635,'0.7238',23)+text(330,635,'0.7318',23)+text(565,635,'0.7592',23)
body+=card(740,410,640,285,'④ 验收与允许差异',['核对元素填充色与色条端点 / 中心','比较文字、位置、裁切与最终尺寸','科学模式锕系范围为 89～103','记录字体、抗锯齿和源参数精度的不确定性','接口测试通过不等于样板复现通过'],'#b45309')
body+=text(60,760,'交付：项目文件 + 三格式图片 + 参数记录 + 参考 / 结果对照 + 差异说明',25,'#0f172a',700)
save('04-reference-check','04 / 如何复现样板','示意色条横置以便讲解；实际样板为竖直色条，底部低值、顶部高值。',body,'无事先约定的像素差分阈值时，应标注“近似复现”，不承诺像素完全一致。')
print(OUT)
