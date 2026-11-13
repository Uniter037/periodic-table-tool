"""Native project payload defaults, validation and pure rendering resolution.

validate_payload returns a complete independent payload, retaining extension keys
and original data values. resolve_payload returns only the validated render style.
"""
from copy import deepcopy
import json

from core.options import (apply_custom_params, LAYOUT_CHOICES, KIND_CHOICES,
                          EDGE_CHOICES, EMPTY_CHOICES, FMT_CHOICES, DPI_CHOICES)
from core.styles import STYLES, CUSTOM_BWR, _make_cmap, _make_norm
from core.scientific import (corrected_style, colorbar_config,
                             validate_render_options, validate_element_overrides)
from core.dataio import convert_data

PARAM_CHOICES = dict(layout=LAYOUT_CHOICES, kind=KIND_CHOICES,
                    edge=EDGE_CHOICES, empty=EMPTY_CHOICES,
                    fmt=FMT_CHOICES, dpi=DPI_CHOICES,
                    rounding=('十进制四舍五入', '原脚本浮点舍入'),
                    crop_mode=('固定画幅', '紧裁切'),
                    cbar_orientation=('vertical', 'horizontal'),
                    cbar_location=('auto', 'left', 'right', 'top', 'bottom'))
DISPLAY_DEFAULTS = dict(show_symbol=True, show_number=True, show_value=True,
                        transparent=False, preserve_cbar_space=False, check_label_overlap=True)
_BASE_PARAMS = dict(cmap='coolwarm', vmin='-1', vcenter='0', vmax='1',
    layout='展开 8-9 行（经典）', kind='热力图', fmt='三位小数', font='Arial',
    edge='无边框', empty='浅灰', dpi='100', figsize='10x5', title='',
    rounding='十进制四舍五入', crop_mode='固定画幅', margins='', cbar_box='',
    symbol_fs='9', number_fs='6', value_fs='6', edge_width='0', edge_color='black',
    value_dx='0', value_dy='0', label_wrap='0', unit='', color_nodes='',
    cbar_orientation='vertical', cbar_location='auto', cbar_label='',
    cbar_fraction='0.046', cbar_pad='0.04', cbar_shrink='1')


def default_payload(mode_id='custom'):
    """Return the complete native preset, with Chinese UI choices and no data."""
    if not isinstance(mode_id, str) or mode_id not in STYLES:
        raise ValueError('未知项目 / 预设样式')
    style = STYLES[mode_id]
    if style.get('kind') != 'cmap':
        style = corrected_style(style)
    params = deepcopy(_BASE_PARAMS)
    for key, choices in PARAM_CHOICES.items():
        if isinstance(choices, dict) and key != 'dpi':
            reverse = {v: k for k, v in choices.items()}
            params[key] = reverse.get(style.get(key), params[key])
    params['edge'] = '黑色细线' if style.get('edge') else '无边框'
    params['edge_width'] = str(style['edge'][0] if style.get('edge') else 0)
    for key in ('font', 'symbol_fs', 'number_fs', 'value_fs', 'value_dx', 'value_dy',
                'label_wrap', 'unit', 'cbar_orientation', 'cbar_location',
                'cbar_fraction', 'cbar_pad', 'cbar_shrink', 'cbar_label'):
        params[key] = str(style.get(key, params[key]))
    cmap = style.get('cmap')
    params['cmap'] = '自定义(蓝-白-红)' if isinstance(cmap, (tuple, list)) else (cmap or '')
    norm = style.get('norm')
    params.update(vmin=str(norm[1]) if norm else '0',
                  vmax=str(norm[-1]) if norm else '1',
                  vcenter=str(norm[2]) if norm and norm[0] == 'twoslope' else '')
    if mode_id == 'custom':
        params.update(vmin='-1', vcenter='0', vmax='1')
    return dict(mode_id=mode_id, compatibility=False, output_format='svg',
                output_dir='', params=params,
                display={k: style.get(k, v) for k, v in DISPLAY_DEFAULTS.items()},
                show_cbar=True, show_cbar_labels=True, cbar_override=None,
                custom_colors=deepcopy(CUSTOM_BWR), data={}, element_overrides={})


PARAM_DEFAULTS = default_payload()['params']


def _resolve(payload):
    style = deepcopy(STYLES[payload['mode_id']])
    if not payload['compatibility'] and style.get('kind') != 'cmap':
        style = corrected_style(style)
    # Validate even disabled legacy parameters, but preserve legacy drawing rules.
    candidate = apply_custom_params(style, payload['params'], payload['display'],
                                    payload['custom_colors'], payload['element_overrides'],
                                    payload['compatibility'])
    candidate = validate_render_options(candidate)
    _make_norm(candidate)
    _make_cmap(candidate)
    if style.get('customizable'):
        style = candidate
    if payload['cbar_override'] is not None:
        style['cbar'] = colorbar_config(payload['cbar_override'])
    if not payload['show_cbar_labels']:
        cfg = style.get('cbar')
        style['cbar'] = ({**cfg, 'labels': [''] * len(cfg['ticks'])} if cfg else
                         dict(ticks=[], labels=[], fontsize=8))
    # show_cbar remains a separate render_table argument; also expose it here.
    style['show_cbar'] = payload['show_cbar']
    style['preserve_cbar_space'] = payload['display']['preserve_cbar_space']
    style['check_label_overlap'] = payload['display']['check_label_overlap']
    return style


def validate_payload(payload):
    """Validate and fill legacy omissions without coercing the stored data."""
    if not isinstance(payload, dict):
        raise ValueError('项目必须是字典')
    result = default_payload(payload.get('mode_id', 'custom'))
    for group, defaults in (('params', result['params']), ('display', result['display'])):
        values = payload.get(group, {})
        if not isinstance(values, dict) or set(values) - set(defaults):
            raise ValueError(f'{group} 含未知参数或格式无效')
        defaults.update(deepcopy(values))
    for key, value in payload.items():
        if key not in ('params', 'display'):
            result[key] = deepcopy(value)
    # Native label/cmap snapshots use an empty format when STYLES has no fmt.
    # The shared GUI rule has always resolved that exact placeholder to 3f.
    if result['params']['fmt'] == '':
        result['params']['fmt'] = _BASE_PARAMS['fmt']
    # Tk StringVar.set(None) serializes the unmapped cmap kind as 'None'.
    if result['mode_id'] == 'cmap_preview' and result['params']['kind'] == 'None':
        result['params']['kind'] = _BASE_PARAMS['kind']
    for key, value in result['params'].items():
        if not isinstance(value, str):
            raise ValueError(f'params.{key} 必须为文本')
        if key in PARAM_CHOICES and value not in PARAM_CHOICES[key]:
            raise ValueError(f'params.{key} 选择无效: {value!r}')
    if 'edge' in payload.get('params', {}) and 'edge_width' not in payload['params']:
        result['params']['edge_width'] = '0.5' if result['params']['edge'] == '黑色细线' else '0'
    for key in ('compatibility', 'show_cbar', 'show_cbar_labels'):
        if not isinstance(result[key], bool):
            raise ValueError(f'{key} 必须为 bool')
    if any(not isinstance(v, bool) for v in result['display'].values()):
        raise ValueError('display 必须为 bool')
    if result['output_format'] not in ('svg', 'png', 'pdf'):
        raise ValueError('输出格式无效')
    if not isinstance(result['output_dir'], str):
        raise ValueError('output_dir 必须为文本')
    validate_element_overrides(result['element_overrides'])
    colorbar_config(result['cbar_override'])
    from matplotlib.colors import is_color_like
    colors = result['custom_colors']
    if (not isinstance(colors, (list, tuple)) or len(colors) < 2 or
            any(not isinstance(c, (list, tuple)) or len(c) != 3 or
                any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in c) or
                not is_color_like(c) for c in colors)):
        raise ValueError('custom_colors 必须为至少两个 RGB 颜色')
    data = result['data']
    if not isinstance(data, dict) or any(
            not isinstance(k, str) or isinstance(v, bool) or
            not isinstance(v, (str, int, float)) for k, v in data.items()):
        raise ValueError('项目数据必须是元素对应文本或数字')
    style = _resolve(result)
    convert_data(data, 'heatmap' if style['kind'] == 'cmap' else style['kind'])
    try:
        json.dumps(result, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError('项目必须为有限 JSON 数据') from exc
    return result


def resolve_payload(payload):
    """Return the validated render style; never mutate payload or STYLES."""
    return _resolve(validate_payload(payload))
