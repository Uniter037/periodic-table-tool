"""Real export acceptance: imported values, zero, typography and file formats."""
from pathlib import Path
import copy
import pytest

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image

from core import STYLES, parse_data, render_table, save_figure


def test_import_to_publication_exports(tmp_path):
    source = Path(__file__).resolve().parents[1] / 'examples' / 'heatmap.txt'
    data = parse_data(source.read_text(encoding='utf-8'))
    assert data['H'] == 0 and min(data.values()) < 0 < max(data.values())
    style = copy.deepcopy(STYLES['custom'])
    style.update(norm=('normalize', min(data.values()), max(data.values())),
                 cbar_orientation='horizontal', cbar_label='测量值',
                 symbol_fs=10, number_fs=6, value_fs=7, fmt='2f',
                 cbar={'ticks': [-1.2, 0, 2.8], 'labels': ['低', '零', '高'], 'fontsize': 9})
    fig = render_table(style, data, title='元素测量结果', figsize=(12, 6))
    try:
        assert '0.00' in [text.get_text() for text in fig.axes[0].texts]
        assert [text.get_text() for text in fig.axes[1].get_xticklabels()] == ['低', '零', '高']
        png = save_figure(fig, str(tmp_path), 'acceptance', 'png', dpi=200)
        svg = save_figure(fig, str(tmp_path), 'acceptance', 'svg')
        pdf = save_figure(fig, str(tmp_path), 'acceptance', 'pdf')
        with Image.open(png) as image:
            assert image.size == (2400, 1200)
            assert image.convert('RGB').getextrema() != ((255, 255),) * 3
        assert '<svg' in Path(svg).read_text(encoding='utf-8')
        assert Path(pdf).read_bytes().startswith(b'%PDF')
        second = save_figure(fig, str(tmp_path), 'acceptance', 'png', dpi=100)
        assert second != png and Path(png).is_file()
    finally:
        plt.close(fig)


def test_chinese_label_data_can_render(tmp_path):
    source = Path(__file__).resolve().parents[1] / 'examples' / 'labels.txt'
    data = parse_data(source.read_text(encoding='utf-8'))
    style = dict(STYLES['custom'], kind='labels', bg='#f0f0f0',
                 value_fs=7, highlight_bg='#dceaf7', highlight_fg='#17395c')
    fig = render_table(style, data)
    try:
        assert '活性中心' in [text.get_text() for text in fig.axes[0].texts]
        assert len(fig.axes) == 1
        path = save_figure(fig, str(tmp_path), 'labels', 'png', dpi=150)
        assert Path(path).stat().st_size > 1000
    finally:
        plt.close(fig)


def test_gui_import_preview_and_export(app, monkeypatch, tmp_path):
    """Use application commands, not a separate rendering shortcut."""
    import main
    errors = []
    monkeypatch.setattr(main.messagebox, 'showerror', lambda *args, **kw: errors.append(args))
    monkeypatch.setattr(main.messagebox, 'showinfo', lambda *args, **kw: None)
    monkeypatch.setattr(main.messagebox, 'askyesno', lambda *args, **kw: False)
    app.mode_combo.current(list(STYLES).index('custom'))
    app._on_style_change()
    source = Path(__file__).resolve().parents[1] / 'examples/heatmap.txt'
    monkeypatch.setattr(main.filedialog, 'askopenfilename', lambda **kw: str(source))
    app._import_file()
    assert app.data['H'].strip() == '0'
    assert app._validated_data('heatmap')['H'] == 0
    app.param_vars['vmin'].set('-1.2')
    app.param_vars['vmax'].set('2.8')
    app.param_vars['vcenter'].set('')
    app.param_vars['figsize'].set('12x6')
    app.param_vars['dpi'].set('150')
    app.param_vars['title'].set('真实工作流验收')
    app.cbar_override = None
    app.show_cbar_var.set(True)
    app.show_cbar_labels_var.set(True)
    app._refresh_preview_now()
    assert app.preview.fig is not None
    assert '0.000' in [text.get_text() for text in app.preview.fig.axes[0].texts]
    app.out_var.set(str(tmp_path))
    for fmt in ('png', 'svg', 'pdf'):
        app.fmt_var.set(fmt)
        app.generate()
        files = list(tmp_path.glob('*.' + fmt))
        assert len(files) == 1, (fmt, errors, app.status_var.get())
        assert files[0].stat().st_size > 1000
        if fmt == 'png':
            with Image.open(files[0]) as image:
                assert image.size == (1800, 900)
    assert not errors


def test_gui_invalid_data_blocks_export(app, monkeypatch, tmp_path):
    import main
    errors = []
    monkeypatch.setattr(main.messagebox, 'showerror', lambda *args, **kw: errors.append(args))
    monkeypatch.setattr(main.messagebox, 'showwarning', lambda *args, **kw: errors.append(args))
    app.mode_combo.current(list(STYLES).index('custom'))
    app._on_style_change()
    app.data = {'Fe': 'not-a-number', 'H': 0}
    app.table.set_data(app.data)
    app.out_var.set(str(tmp_path))
    app.fmt_var.set('png')
    app.generate()
    assert not list(tmp_path.glob('*.png'))
    assert errors or '失败' in app.status_var.get() or '无效' in app.status_var.get()


def test_unknown_symbols_cannot_disappear_during_edit(app):
    app.data = {'H': 1}
    app.table.set_data(app.data)
    with pytest.raises(ValueError, match='Xx'):
        app._import_text('H,1\nXx,2')
    assert app.data == {'H': 1}
    app.data = {'H': 1, 'Xx': 2}  # 模拟旧预设
    app.table.set_data({'H': 3})
    app._table_changed()
    assert app.data == {'H': '3', 'Xx': 2}
