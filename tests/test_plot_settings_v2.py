"""Run GUI cases in isolated interpreters: never add a second Tk to the suite."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


_BOOT = '''
import json
import sys
import tkinter as tk
from copy import deepcopy
from tkinter import ttk
from domain.plot_spec import PlotSpec
from ui.plot_settings_v2 import PlotSettingsPanel, _GROUPS
root = tk.Tk()
root.withdraw()
changes, errors = [], []
panel = PlotSettingsPanel(root, changes.append, errors.append)
panel.pack(fill='both', expand=True)
def settle():
    root.after(450, root.quit)
    root.mainloop()
def edit(key, value):
    panel._vars[key].set(value)
'''


_CASES = {
    'native_roundtrip': '''
plot = PlotSpec.from_dict({
    'kind': 'labels', 'layout': 'compact', 'font': 'Microsoft YaHei',
    'title': '中文标题', 'transparent': True, 'margins': [.1,.2,.8,.9],
    'cbar_box': [.8,.2,.05,.6], 'edge': [1.2,[0,0,0,.5]],
    'cmap': ['custom', [[0,0,1], [1,1,1], [1,0,0]]],
    'cbar': {'ticks': [-1,0,1], 'labels': ['低','中','高'], 'visible': [True,False,True], 'fontsize': 12},
    'show_cbar_labels': False,
    'element_overrides': {'Fe': {'show_color': False, 'include_in_range': False, 'value_dx': 3}}
}).to_dict()
before = deepcopy(plot)
panel.set_plot(plot)
assert panel.get_plot() == before
plot['cbar']['labels'][0] = '外部修改'
assert panel.get_plot() == before
snapshot = panel.get_plot()
snapshot['element_overrides'].clear()
assert panel.get_plot() == before
settle()
assert changes == []
assert not errors
''',
    'debounce_minimal_patch': '''
edit('title', '第一版')
edit('title', '最终标题')
edit('dpi', '240')
settle()
assert changes == [{'title': '最终标题', 'dpi': 240}]
assert not errors
panel._commit()
assert len(changes) == 1
''',
    'invalid_no_reset': '''
edit('dpi', '不是数字')
edit('title', '保留草稿')
settle()
assert not changes and errors
assert panel._vars['dpi'].get() == '不是数字'
assert panel._vars['title'].get() == '保留草稿'
try:
    panel.get_plot()
except ValueError:
    pass
else:
    raise AssertionError('invalid get_plot must fail')
edit('dpi', '200')
settle()
assert changes == [{'title': '保留草稿', 'dpi': 200}]
assert panel.error_var.get() == ''
''',
    'range_and_orientation_atomic': '''
edit('norm_mode', '线性')
edit('norm_min', '2')
edit('norm_max', '5')
edit('cbar_orientation', '水平')
edit('cbar_location', '下方')
settle()
assert changes == [{'norm': ['normalize',2,5], 'cbar_orientation': 'horizontal', 'cbar_location': 'bottom'}]
edit('norm_mode', '中心分段')
edit('norm_center', '3')
settle()
assert changes[-1] == {'norm': ['twoslope',2,3,5]}
edit('norm_center', '6')
settle()
assert len(changes) == 2 and errors
assert panel._vars['norm_center'].get() == '6'
''',
    'colourbar_rows': '''
panel.bar_enabled.set(True)
panel._add_bar_row(-1, '低', True)
panel._add_bar_row(0, '隐藏', False)
panel._add_bar_row(1, '高', True)
edit('bar_fontsize', '11')
edit('show_cbar_labels', False)
settle()
bar = panel.get_plot()['cbar']
assert bar == dict(ticks=[-1,0,1], labels=['低','隐藏','高'], visible=[True,False,True], fontsize=11)
assert changes[-1] == {'cbar': bar, 'show_cbar_labels': False}
panel._bar_rows[1][1][1].set('隐藏已修改')
panel._bar_rows[1][1][2].set(True)
settle()
assert panel.get_plot()['cbar']['labels'][1] == '隐藏已修改'
panel._remove_row(panel._bar_rows, panel._bar_rows[0])
settle()
assert panel.get_plot()['cbar']['ticks'] == [0,1]
panel._bar_rows[0][1][0].set('1')
settle()
assert errors and panel._bar_rows[0][1][0].get() == '1'
panel._bar_rows[0][1][0].set('0')
panel.bar_enabled.set(False)
settle()
assert panel.get_plot()['cbar'] is None
assert len(panel._bar_rows) == 2
panel.bar_enabled.set(True)
settle()
assert panel.get_plot()['cbar']['ticks'] == [0,1]
''',
    'colors_geometry': '''
panel.custom_cmap.set(True)
panel._add_node('.5', '#ffffff')
for key, values in {'margins': [.15,.2,.85,.9], 'cbar_box': [.9,.2,.05,.6], 'edge': [2,'#123456']}.items():
    panel._enabled[key].set(True)
    for var, value in zip(panel._vars[key], values):
        var.set(value)
settle()
plot = panel.get_plot()
assert plot['margins'] == [.15,.2,.85,.9]
assert plot['cbar_box'] == [.9,.2,.05,.6]
assert plot['edge'] == [2,'#123456']
assert plot['cmap'] == ['custom', [[0,'#0000ff'],[.5,'#ffffff'],[1,'#ff0000']]]
assert set(changes[-1]) == {'margins','cbar_box','edge','cmap'}
panel._vars['cbar_box'][2].set('.2')
settle()
assert errors and len(changes) == 1
''',
    'advanced_overrides_and_full_spec': '''
panel._apply_advanced({'Fe': {'show_value': False, 'show_color': False, 'include_in_range': False, 'value_dx': 2.5, 'value_dy': -3}}, 'element_overrides')
settle()
assert changes[-1] == {'element_overrides': {'Fe': {'show_value': False, 'show_color': False, 'include_in_range': False, 'value_dx': 2.5, 'value_dy': -3}}}
plot = panel.get_plot()
plot['highlight_bg'] = [1,0,0,.5]
plot['font'] = '中文字体'
panel._apply_advanced(plot)
settle()
assert changes[-1] == {'highlight_bg': [1,0,0,.5], 'font': '中文字体'}
before = panel.get_plot()
try:
    panel._apply_advanced({'Xx': {}}, 'element_overrides')
except ValueError:
    pass
else:
    raise AssertionError('bad override accepted')
assert panel.get_plot() == before
''',
    'set_plot_cancels_pending': '''
edit('title', '不应提交')
panel.set_plot({'dpi': 180})
settle()
assert not changes
assert panel.get_plot() == PlotSpec.from_dict({'dpi':180}).to_dict()
try:
    panel.set_plot({'dpi': 0})
except ValueError:
    pass
else:
    raise AssertionError('invalid set accepted')
assert panel.get_plot()['dpi'] == 180
''',
    'all_fields_search_and_scroll': '''
covered = {key for _, fields in _GROUPS for key, _ in fields}
covered.update(('norm','cmap','cbar','element_overrides'))
assert covered == set(PlotSpec().to_dict())
root.deiconify()
root.geometry('480x500')
root.update()
panel.search_var.set('cbar_box')
root.update()
visible = [frame for frame, _ in panel._sections if frame.winfo_manager()]
assert len(visible) == 1 and visible[0].cget('text') == '精确几何'
panel.search_var.set('不存在的字段')
root.update()
assert not any(frame.winfo_manager() for frame, _ in panel._sections)
panel.search_var.set('')
root.update()
assert all(frame.winfo_manager() for frame, _ in panel._sections)
panel.canvas.yview_moveto(0)
panel._scroll(5)
root.update()
assert panel.canvas.yview()[0] > 0
assert not root.bind_all('<MouseWheel>')
''',
    'callback_failure_retry_and_destroy': '''
def fail(patch):
    raise ValueError('父容器拒绝')
panel.on_change = fail
edit('title', '保留')
settle()
assert errors[-1] == '父容器拒绝'
assert panel._baseline['title'] == ''
assert panel.get_plot()['title'] == '保留'
panel.on_change = changes.append
panel._commit()
assert changes == [{'title': '保留'}]
edit('title', '销毁时取消')
panel.destroy()
settle()
assert len(changes) == 1
''',
    'no_legacy_imports': '''
assert not any(n in sys.modules for n in ['main', 'options', 'scientific', 'styles'])
assert not any(n.startswith(('matplotlib', 'core.')) for n in sys.modules)
''',
}


_CASES['all_native_fields_roundtrip'] = """
plot = PlotSpec.from_dict(dict(
    kind='labels', layout='compact', cmap=['custom', [[0,'blue'], [.4,[1,1,1,.7]], [1,'red']]],
    norm=['normalize', 2, 10], fmt='scientific', rounding='python', font='宋体',
    figsize=[12.125,6.75], dpi=300, title='标题', show_cbar=False, show_cbar_labels=False,
    preserve_cbar_space=True, check_label_overlap=False, bbox_tight=True, transparent=True,
    show_symbol=False, show_number=False, show_value=False, symbol_fs=14, number_fs=7,
    value_fs=10, value_dx=.2, value_dy=-.3, label_wrap=12, unit='克', edge=[.7,'black'],
    empty=[.2,.3,.4,1], bg='white', label_color=[1,0,0], label_fs=11, label_dy=.15,
    num_x=.35, num_ha='right', highlight_bg='red', highlight_fg='white', plain_bg='gray', plain_fg='black',
    margins=[.123456789,.13,.87,.91], cbar_box=[.9,.2,.03,.6],
    cbar=dict(ticks=[2,10], labels=['低','高'], visible=[False,True], fontsize=13),
    cbar_orientation='horizontal', cbar_location='top', cbar_label='浓度',
    cbar_fraction=.07, cbar_pad=.12, cbar_shrink=.8,
    element_overrides={'H': {'show_value':False,'show_color':True,'include_in_range':False,'value_dx':4,'value_dy':-4}}
)).to_dict()
panel.set_plot(plot)
assert panel.get_plot() == plot
settle()
assert changes == []
edit('title', '新标题')
settle()
assert changes == [{'title':'新标题'}]
assert panel.get_plot() == dict(plot, title='新标题')
"""

_CASES['reentrant_parent_and_dialog_cancel'] = """
def owner(patch):
    changes.append(patch)
    state = panel.get_plot()
    state['dpi'] = 222
    panel.set_plot(state)
panel.on_change = owner
edit('title', '父容器同步更新')
settle()
assert panel.get_plot()['dpi'] == 222
panel._commit()
assert len(changes) == 1
panel._json_dialog('element_overrides')
dialog = next(child for child in panel.winfo_children() if isinstance(child, tk.Toplevel))
dialog.destroy()
settle()
assert len(changes) == 1
"""


_CASES['figsize_units_native_storage'] = """
panel.set_plot({'figsize': [10,5]})
panel.figsize_unit.set('毫米')
assert [float(v.get()) for v in panel._vars['figsize']] == [254,127]
assert panel.get_plot()['figsize'] == [10,5]
settle()
assert not changes
panel._vars['figsize'][0].set('203.2')
panel._vars['figsize'][1].set('101.6')
settle()
assert changes == [{'figsize':[8,4]}]
panel.figsize_unit.set('英寸')
assert [float(v.get()) for v in panel._vars['figsize']] == [8,4]
settle()
assert len(changes) == 1
# Incoming session snapshots retain the selected display unit.
panel.figsize_unit.set('毫米')
panel.set_plot({'figsize':[12.123456789123,6.654321987654]})
original = panel.get_plot()['figsize']
for _ in range(20):
    panel.figsize_unit.set('英寸')
    panel.figsize_unit.set('毫米')
assert panel.get_plot()['figsize'] == original
settle()
assert len(changes) == 1
"""

_CASES['figsize_unit_invalid_and_pending_draft'] = """
panel._vars['figsize'][0].set('12')
panel.figsize_unit.set('毫米')
settle()
assert changes == [{'figsize':[12,5]}]
panel._vars['figsize'][0].set('错误')
panel.figsize_unit.set('英寸')
assert panel.figsize_unit.get() == '毫米'
assert panel._vars['figsize'][0].get() == '错误'
settle()
assert len(changes) == 1 and errors
try:
    panel.get_plot()
except ValueError:
    pass
else:
    raise AssertionError('invalid size silently recovered')
panel._vars['figsize'][0].set('254')
settle()
assert changes[-1] == {'figsize':[10,5]}
"""


@pytest.mark.parametrize('case', _CASES)
def test_plot_settings_panel_in_subprocess(case):
    code = _BOOT + '\ntry:\n' + textwrap.indent(textwrap.dedent(_CASES[case]), '    ') + '\nfinally:\n    root.destroy()\n'
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1],
                            env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
