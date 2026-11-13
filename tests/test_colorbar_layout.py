import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pytest
from application.project_codec import default_payload, validate_payload, resolve_payload
from core.styles import render_table

@pytest.mark.parametrize('orientation', ['vertical', 'horizontal'])
@pytest.mark.parametrize('box', [None, '.80,.2,.03,.6'])
@pytest.mark.parametrize('margins', ['', '.08,.08,.75,.9'])
def test_preserved_bounds(orientation, box, margins):
    payload = default_payload()
    payload['params'].update(cbar_orientation=orientation, margins=margins)
    if box:
        payload['params']['cbar_box'] = box if orientation == 'vertical' else '.2,.05,.6,.03'
    payload['display']['preserve_cbar_space'] = True
    style = resolve_payload(payload)
    visible = render_table(style, {'H': .5}, show_cbar=True)
    hidden = render_table(style, {'H': .5}, show_cbar=False)
    try:
        visible.canvas.draw(); hidden.canvas.draw()
        assert hidden.axes[0].get_position().bounds == pytest.approx(visible.axes[0].get_position().bounds)
        assert len(hidden.axes) == 1
        text = hidden.axes[0].texts[0]
        assert text._ptable_element and text._ptable_role
        assert len(text._ptable_cell) == 4
    finally:
        plt.close(visible); plt.close(hidden)

@pytest.mark.parametrize('compatibility', [False, True])
def test_codec(compatibility):
    payload = default_payload('custom')
    payload['compatibility'] = compatibility
    assert payload['display']['preserve_cbar_space'] is False
    assert payload['display']['check_label_overlap'] is True
    payload['display'].update(preserve_cbar_space=True, check_label_overlap=False)
    restored = validate_payload(json.loads(json.dumps(payload)))
    style = resolve_payload(restored)
    assert style['preserve_cbar_space'] is True
    assert style['check_label_overlap'] is False
    payload['display'] = {}
    assert validate_payload(payload)['display']['preserve_cbar_space'] is False
