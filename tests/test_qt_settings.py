"""Each Qt case uses an offscreen subprocess, never the suite's Tk interpreter."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


_BOOT = '''
import sys
from copy import deepcopy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLineEdit, QDialogButtonBox, QPlainTextEdit
from PySide6.QtTest import QTest
from domain.plot_spec import PlotSpec
from ui.qt.settings import PlotSettingsPanel, _GROUPS
app = QApplication([])
changes, errors = [], []
panel = PlotSettingsPanel(on_change=changes.append, on_error=errors.append)
panel.resize(560, 720)
panel.show()
app.processEvents()
def edit(key, value):
    field = panel.fields[key]
    if isinstance(field, QLineEdit):
        field.setText(str(value))
    elif hasattr(field, 'setChecked'):
        field.setChecked(value)
    else:
        field.setCurrentIndex(field.findData(value))
'''

_CASES = {
    'roundtrip_all_fields': '''
plot = PlotSpec.from_dict(dict(
    kind='labels', layout='compact', cmap=['custom', [[0,0,1], [1,1,1], [1,0,0]]],
    norm=['normalize', 2, 10], fmt='scientific', rounding='python', font='宋体',
    figsize=[12.123456789123,6.654321987654], dpi=300, title='标题', show_cbar=False, show_cbar_labels=False,
    preserve_cbar_space=True, check_label_overlap=False, bbox_tight=True, transparent=True,
    show_symbol=False, show_number=False, show_value=False, symbol_fs=14, number_fs=7,
    value_fs=10, value_dx=.2, value_dy=-.3, label_wrap=12, unit='克', edge=[.7,[0,0,0,.5]],
    empty=[.2,.3,.4,1], bg='white', label_color=[1,0,0], label_fs=11, label_dy=.15,
    num_x=.35, num_ha='right', highlight_bg='red', highlight_fg='white', plain_bg='gray', plain_fg='black',
    margins=[.123456789,.13,.87,.91], cbar_box=[.9,.2,.03,.6],
    cbar=dict(ticks=[2,10], labels=['低','高'], visible=[False,True], fontsize=13),
    cbar_orientation='horizontal', cbar_location='top', cbar_label='浓度',
    cbar_fraction=.07, cbar_pad=.12, cbar_shrink=.8,
    element_overrides={'H': {'show_value':False,'show_color':True,'include_in_range':False,'value_dx':4,'value_dy':-4}}
)).to_dict()
before = deepcopy(plot)
panel.set_plot(plot)
assert panel.get_plot() == before
plot['cbar']['labels'].clear()
output = panel.get_plot()
output['element_overrides'].clear()
assert panel.get_plot() == before
QTest.qWait(400)
assert not changes and not errors
assert panel.flush() is True
assert not changes
covered = {key for _, _, fields in _GROUPS for key, _ in fields}
covered.update(('cmap','norm','cbar','element_overrides'))
assert covered == set(before)
''',
    'draft_and_minimal_patch': '''
edit('title', '第一次')
edit('title', '最终标题')
edit('dpi', '240')
assert panel.get_plot()['title'] == '最终标题'
assert not changes
assert panel.flush() is True
assert changes == [{'title': '最终标题', 'dpi':240}]
assert not panel.timer.isActive()
assert panel.flush() is True
assert len(changes) == 1
''',
    'debounce': '''
edit('title', 'a')
QTest.qWait(100)
edit('title', 'b')
QTest.qWait(100)
assert not changes
QTest.qWait(350)
assert changes == [{'title':'b'}]
''',
    'invalid_draft_recovery': '''
edit('dpi', '非法数值')
edit('title', '仍在草稿')
assert panel.flush() is False
assert errors and not changes
assert panel.fields['dpi'].text() == '非法数值'
assert panel.fields['title'].text() == '仍在草稿'
try:
    panel.get_plot()
except ValueError:
    pass
else:
    raise AssertionError('get_plot accepted invalid draft')
edit('dpi', '200')
assert panel.flush()
assert changes == [{'title':'仍在草稿','dpi':200}]
assert panel.error_label.text() == ''
''',
    'callback_rejection_retry': '''
original = deepcopy(panel._baseline)
def reject(patch):
    patch.clear()
    raise ValueError('会话拒绝颜色')
panel.on_change = reject
edit('bg', 'session-will-check-this-color')
edit('title', '待重试')
assert panel.flush() is False
assert panel._baseline == original
assert panel.get_plot()['bg'] == 'session-will-check-this-color'
assert errors[-1] == '会话拒绝颜色'
panel.on_change = changes.append
assert panel.flush()
assert changes == [{'bg':'session-will-check-this-color','title':'待重试'}]
''',
    'set_plot_and_unknown_fields': '''
edit('title', '取消的修改')
panel.set_plot({'dpi':180})
assert not panel.timer.isActive()
QTest.qWait(400)
assert not changes
before = panel.get_plot()
for value in ({'dpi':0}, {'unknown_field':123}):
    try:
        panel.set_plot(value)
    except ValueError:
        pass
    else:
        raise AssertionError('invalid input accepted')
assert panel.get_plot() == before
try:
    panel.apply_advanced(dict(before, unknown_field=123))
except ValueError:
    pass
else:
    raise AssertionError('unknown advanced field silently dropped')
assert panel.get_plot() == before
''',
    'millimeters_and_precision': '''
panel.set_plot({'figsize':[10,5]})
panel.figsize_unit.setCurrentText('毫米')
assert [float(w.text()) for w in panel.fields['figsize']] == [254,127]
assert panel.get_plot()['figsize'] == [10,5]
assert panel.flush() and not changes
for field, text in zip(panel.fields['figsize'], ['203.2','101.6']):
    field.setText(text)
assert panel.flush()
assert changes == [{'figsize':[8,4]}]
panel.figsize_unit.setCurrentText('英寸')
assert [float(w.text()) for w in panel.fields['figsize']] == [8,4]
panel.set_plot({'figsize':[12.123456789123,6.654321987654]})
original = panel.get_plot()['figsize']
for _ in range(20):
    panel.figsize_unit.setCurrentText('毫米')
    panel.figsize_unit.setCurrentText('英寸')
assert panel.get_plot()['figsize'] == original
assert panel.flush() and len(changes) == 1
assert 'figsize_unit' not in panel.get_plot()
''',
    'invalid_unit_change_preserves_draft': '''
panel.fields['figsize'][0].setText('12')
panel.figsize_unit.setCurrentText('毫米')
assert panel.flush()
assert changes == [{'figsize':[12,5]}]
panel.fields['figsize'][0].setText('坏数据')
panel.figsize_unit.setCurrentText('英寸')
assert panel.figsize_unit.currentText() == '毫米'
assert panel.fields['figsize'][0].text() == '坏数据'
assert panel.flush() is False
assert len(changes) == 1 and errors
''',
    'range_orientation_atomic': '''
panel.norm_mode.setCurrentIndex(panel.norm_mode.findData('normalize'))
panel.norm_fields[0].setText('2')
panel.norm_fields[2].setText('5')
edit('cbar_orientation','horizontal')
edit('cbar_location','bottom')
assert panel.flush()
assert changes == [{'norm':['normalize',2,5], 'cbar_orientation':'horizontal','cbar_location':'bottom'}]
panel.norm_mode.setCurrentIndex(panel.norm_mode.findData('twoslope'))
panel.norm_fields[1].setText('3')
assert panel.flush()
assert changes[-1] == {'norm':['twoslope',2,3,5]}
panel.norm_fields[1].setText('6')
assert not panel.flush()
assert len(changes) == 2
edit('cbar_location','left')
assert not panel.flush()
''',
    'cbar_edit_hide_delete': '''
panel.bar_enabled.setChecked(True)
panel.add_cbar_row(-1,'低',True)
panel.add_cbar_row(0,'隐藏',False)
panel.add_cbar_row(1,'高',True)
panel.bar_fontsize.setText('11')
edit('show_cbar_labels',False)
assert panel.flush()
bar = panel.get_plot()['cbar']
assert bar == dict(ticks=[-1,0,1],labels=['低','隐藏','高'],visible=[True,False,True],fontsize=11)
assert changes[-1] == {'cbar':bar,'show_cbar_labels':False}
panel.cbar_table.item(1,1).setText('编辑后')
panel.cbar_table.item(1,2).setCheckState(Qt.CheckState.Checked)
assert panel.flush()
assert panel.get_plot()['cbar']['labels'][1] == '编辑后'
panel.cbar_table.selectRow(0)
panel._delete_rows(panel.cbar_table)
assert panel.flush()
assert panel.get_plot()['cbar']['ticks'] == [0,1]
panel.cbar_table.item(0,0).setText('1')
assert not panel.flush()
panel.cbar_table.item(0,0).setText('0')
panel.bar_enabled.setChecked(False)
assert panel.flush() and panel.get_plot()['cbar'] is None
assert panel.cbar_table.rowCount() == 2
panel.bar_enabled.setChecked(True)
assert panel.flush()
assert panel.get_plot()['cbar']['ticks'] == [0,1]
''',
    'nodes_geometry_and_palette_preservation': '''
panel.custom_cmap.setChecked(True)
panel.add_color_node(.5,'#ffffff')
for key, values in {'margins':[.15,.2,.85,.9], 'cbar_box':[.9,.2,.05,.6], 'edge':[2,'#123456']}.items():
    panel._enabled[key].setChecked(True)
    for field, value in zip(panel.fields[key],values):
        field.setText(str(value))
assert panel.flush()
plot = panel.get_plot()
assert plot['cmap'] == ['custom',[[0,'#0000ff'],[.5,'#ffffff'],[1,'#ff0000']]]
assert plot['margins'] == [.15,.2,.85,.9]
assert plot['cbar_box'] == [.9,.2,.05,.6]
assert plot['edge'] == [2,'#123456']
assert set(changes[-1]) == {'cmap','margins','cbar_box','edge'}
panel.fields['cbar_box'][2].setText('.2')
assert not panel.flush()
assert len(changes) == 1
panel.set_plot({'cmap':['custom',['blue','white','red']]})
assert panel.get_plot()['cmap'] == ['custom',['blue','white','red']]
edit('dpi',144)
assert panel.flush() and changes[-1] == {'dpi':144}
''',
    'advanced_and_dialog_validation': '''
panel.apply_advanced({'Fe':{'show_value':False,'include_in_range':False,'value_dx':4}}, 'element_overrides')
assert panel.get_plot()['element_overrides']['Fe']['value_dx'] == 4
assert panel.flush()
assert set(changes[-1]) == {'element_overrides'}
before = panel.get_plot()
try:
    panel.apply_advanced({'Xx':{}},'element_overrides')
except ValueError:
    pass
else:
    raise AssertionError('invalid override accepted')
assert panel.get_plot() == before
dialog = panel.open_advanced()
editor = dialog.findChild(QPlainTextEdit,'advanced_json')
buttons = dialog.findChild(QDialogButtonBox)
editor.setPlainText('{bad json')
buttons.button(QDialogButtonBox.StandardButton.Ok).click()
assert dialog.isVisible() and errors
assert panel.get_plot() == before
import json
editor.setPlainText(json.dumps(dict(before,title='高级标题')))
buttons.button(QDialogButtonBox.StandardButton.Ok).click()
assert not dialog.isVisible()
assert panel.get_plot()['title'] == '高级标题'
assert panel.flush() and changes[-1] == {'title':'高级标题'}
''',
    'search_and_no_legacy_imports': '''
panel.search.setText('cbar_box')
app.processEvents()
visible = [panel.tabs.tabText(i) for i in range(panel.tabs.count()) if panel.tabs.isTabVisible(i)]
assert visible == ['几何']
panel.search.setText('毫米')
app.processEvents()
assert [panel.tabs.tabText(i) for i in range(panel.tabs.count()) if panel.tabs.isTabVisible(i)] == ['基本']
panel.search.setText('没有该字段')
app.processEvents()
assert panel.no_results.isVisible()
panel.search.clear()
app.processEvents()
assert all(panel.tabs.isTabVisible(i) for i in range(panel.tabs.count()))
assert panel.width() == 560
assert not any(n in sys.modules for n in ('tkinter','main','options','styles','scientific','ui.plot_settings_v2'))
assert not any(n.startswith(('matplotlib','core.')) for n in sys.modules)
''',
    'optional_callback_and_reentrant_owner': '''
panel.on_change = None
edit('title','无回调')
assert panel.flush()
assert panel._baseline['title'] == '无回调'
def owner(patch):
    changes.append(patch)
    state = panel.get_plot()
    state['dpi'] = 222
    panel.set_plot(state)
panel.on_change = owner
edit('title','同步回填')
assert panel.flush()
assert panel.get_plot()['dpi'] == 222
assert panel.flush() and len(changes) == 1
''',
}


_CASES['public_section_navigation'] = """
panel.search.setText('cbar_box')
assert panel.select_section('色条') is True
assert panel.search.text() == ''
assert panel.tabs.tabText(panel.tabs.currentIndex()) == '色条'
for name, title in [('图形','基本'),('字体','文本'),('配色','配色'),('范围','配色'),('几何','几何'),('高级','高级')]:
    assert panel.select_section(name) is True
    assert panel.tabs.tabText(panel.tabs.currentIndex()) == title
panel.search.setText('norm')
current = panel.tabs.currentIndex()
assert panel.select_section('不存在的分组') is False
assert panel.search.text() == 'norm' and panel.tabs.currentIndex() == current
assert panel.flush() and changes == []
"""


@pytest.mark.parametrize('case', _CASES)
def test_qt_settings_offscreen(case):
    code = _BOOT + '\ntry:\n' + textwrap.indent(textwrap.dedent(_CASES[case]), '    ') + '\nfinally:\n    panel.timer.stop()\n    panel.close()\n    app.quit()\n'
    result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1],
        env=dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONIOENCODING='utf-8'),
        capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
