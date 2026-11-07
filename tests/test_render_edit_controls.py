from copy import deepcopy
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pytest
from core.styles import STYLES, render_table, _fmt_value
from core.scientific import validate_element_overrides, validate_render_options, corrected_style, range_data, range_warnings

@pytest.mark.parametrize('value,fmt,expected', [(2.675,'2f','2.68'),(-2.675,'2f','-2.68'),(.02675,'percent2','2.68%'),(1.2345,'scientific','1.235e+00'),(9.9995,'scientific','1.000e+01'),(.00012345,'scientific','1.235e-04'),(0,'scientific','0.000e+00')])
def test_rounding(value, fmt, expected):
    assert _fmt_value(value, fmt, 'half_up') == expected
    assert _fmt_value(value, fmt) == _fmt_value(value, fmt, 'legacy')

@pytest.mark.parametrize('options', [{'Xx':{}},{'H':{'show_value':1}},{'H':{'show_color':'false'}},{'H':{'include_in_range':0}},{'H':{'value_dx':float('inf')}},{'H':{'value_dy':True}},{'H':{'oops':False}},[]])
def test_invalid_overrides(options):
    with pytest.raises(ValueError): validate_element_overrides(options)

def test_independent_edits_and_range():
    original={'H':{'show_color':False,'include_in_range':False}}
    result=validate_element_overrides(original)
    result['H']['show_color']=True
    assert original['H']['show_color'] is False
    data={'H':100,'He':0}
    style=dict(STYLES['custom'],element_overrides=original)
    assert range_data(style,data)=={'He':0}
    assert range_warnings(style,{'H':100})==[]
    assert data=={'H':100,'He':0}

@pytest.mark.parametrize('key,value', [('margins',(0,0,1,1)),('cbar_box',(.8,.2,.05,.6))])
def test_boxes_valid(key,value):
    assert validate_render_options(dict(STYLES['custom'], **{key:value}))[key]==value

@pytest.mark.parametrize('key,value', [('margins',(0,0,0,1)),('margins',(-.1,0,1,1)),('margins',(0,False,1,1)),('cbar_box',(.9,.2,.2,.5)),('cbar_box',(0,0,0,1)),('cbar_box',(0,0,float('nan'),1)),('cbar_box','0,0,1,1')])
def test_boxes_invalid(key,value):
    with pytest.raises(ValueError): validate_render_options(dict(STYLES['custom'], **{key:value}))

def test_offsets_visibility_and_source():
    data={'H':2.675,'He':1}
    style=dict(STYLES['custom'],fmt='2f',value_dx=.1,value_dy=.2)
    fig=render_table(style,data,show_cbar=False)
    try:
        original=next(t.get_position() for t in fig.axes[0].texts if t.get_text()=='2.68')
    finally: plt.close(fig)
    style['element_overrides']={'H':{'value_dx':.3,'value_dy':-.4,'show_color':False},'He':{'show_value':False}}
    fig=render_table(style,data,show_cbar=False)
    try:
        text=next(t for t in fig.axes[0].texts if t.get_text()=='2.68')
        assert text.get_position()==pytest.approx((original[0]+.3,original[1]-.4))
        assert '1.00' not in [t.get_text() for t in fig.axes[0].texts]
        from matplotlib.colors import to_rgba
        assert fig.axes[0].patches[0].get_facecolor()==to_rgba(style['empty'])
        assert data=={'H':2.675,'He':1}
    finally: plt.close(fig)

@pytest.mark.parametrize('margins',[None,(.1,.2,.8,.9)])
@pytest.mark.parametrize('orientation',['vertical','horizontal'])
def test_manual_cbar_preserves_main(margins,orientation):
    style=dict(STYLES['custom'],cbar_orientation=orientation)
    if margins: style['margins']=margins
    reference=render_table(style,{'H':.7},show_cbar=margins is None)
    fig=render_table(dict(style,cbar_box=(.85,.2,.05,.6)),{'H':.7})
    try:
        fig.canvas.draw(); reference.canvas.draw()
        assert fig.axes[0].get_position().bounds==pytest.approx(reference.axes[0].get_position().bounds)
        assert fig.axes[1].get_position().bounds==pytest.approx((.85,.2,.05,.6))
    finally: plt.close(fig); plt.close(reference)

def test_marker_and_rounding_modes():
    for style,marker,value in [(STYLES['reconstruct_2f_a'],'86~103','2.67'),(corrected_style(STYLES['reconstruct_2f_a']),'89~103','2.68')]:
        fig=render_table(style,{'H':2.675},show_cbar=False)
        try:
            texts=[t.get_text() for t in fig.axes[0].texts]
            assert marker in texts and value in texts
        finally: plt.close(fig)

def test_manual_box_raster_hit_geometry():
    from core.imaging import rasterize
    style=dict(STYLES['custom'],cbar_box=(.88,.2,.04,.6),margins=(.08,.15,.8,.9))
    fig=render_table(style,{'H':.7})
    try:
        for tight in (False,True):
            image,hits=rasterize(fig,{(0,9.9,1,10.9):'H'},tight=tight)
            assert image.width>0 and image.height>0
            assert list(hits.values())==['H']
            assert fig.axes[1].get_position().bounds==pytest.approx((.88,.2,.04,.6))
    finally: plt.close(fig)
