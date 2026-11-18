"""Pure, explicit migration of native project snapshots to schema 2.

MigrationError.report describes a blocked migration; no partial document is
published. Unknown document/payload metadata is retained, never used as config.
"""
from copy import deepcopy
import hashlib
import json

from application.project_codec import resolve_payload
from application.dataset_collection import DatasetCollection
from core.dataio import convert_data
from domain.plot_spec import PlotSpec


# Deliberate allowlist: legacy control flags must never reach the new renderer.
_SPEC_FIELDS = """kind layout cmap norm fmt rounding font figsize dpi title
show_cbar show_cbar_labels preserve_cbar_space check_label_overlap bbox_tight
transparent show_symbol show_number show_value symbol_fs number_fs value_fs
value_dx value_dy label_wrap unit edge empty bg label_color label_fs label_dy
num_x num_ha highlight_bg highlight_fg plain_bg plain_fg margins cbar_box cbar
cbar_orientation cbar_location cbar_label cbar_fraction cbar_pad cbar_shrink
element_overrides""".split()


class MigrationError(ValueError):
    """A migration cannot safely produce a schema-2 document."""

    def __init__(self, message, report):
        super().__init__(message)
        self.report = deepcopy(report)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _validate_data(payload, path, kind):
    data = payload.get('data')
    if not isinstance(data, dict) or any(
        not isinstance(k, str) or isinstance(v, bool) or
        not isinstance(v, (str, int, float)) for k, v in data.items()
    ):
        raise ValueError(f'{path}.data must map element names to raw text/numbers')
    try:
        convert_data(data, kind)  # Validate only; lexical values remain untouched.
    except (ValueError, OverflowError) as exc:
        raise ValueError(f'{path}.data: {exc}') from exc


def _validate_excel(snapshot):
    collection = (DatasetCollection.from_snapshot(deepcopy(snapshot['excel_collection']))
                  if 'excel_collection' in snapshot else DatasetCollection())
    attached = snapshot.get('excel_attached', False)
    if type(attached) is not bool or (attached and collection.active_dataset_id is None):
        raise ValueError('Invalid Excel association: excel_attached requires an active dataset')


def _payload(payload, path, report):
    if not isinstance(payload, dict):
        raise ValueError(f'{path} must be an object')
    effective = resolve_payload(payload)
    if effective['kind'] == 'cmap':
        report['unsupported_fields'].append(dict(path=f'{path}.kind', value='cmap',
            reason='Colormap preview is a separate tool, not a periodic-table plot'))
        return None
    spec = PlotSpec.from_dict({}).to_dict()
    for field in _SPEC_FIELDS:
        if field in effective:
            spec[field] = deepcopy(effective[field])
    spec['layout'] = {'classic': 'expanded', 'reconstructed': 'compact'}[effective['layout']]
    modern = effective.get('id') == 'custom' or effective.get('corrected', False)
    if 'label_color' not in effective:
        spec['label_color'] = 'black'
    if modern and effective['kind'] == 'labels' and 'value_fs' in effective:
        # The former draw_text overrode label_fs with value_fs for measurements.
        spec['label_fs'] = effective['value_fs']
    spec['rounding'] = ('python' if not modern or effective.get('rounding') == 'legacy'
                        else 'half_up')
    spec['title'] = payload.get('params', {}).get('title', '') if effective.get('customizable') else ''
    spec['show_cbar_labels'] = payload.get('show_cbar_labels', True)
    # resolve_payload/colorbar_config intentionally filters hidden rows. Storage
    # must retain them, including labels while the global label switch is off.
    override = payload.get('cbar_override')
    if override is not None:
        spec['cbar'] = deepcopy(override)
        spec['cbar'].setdefault('visible', [True] * len(override['ticks']))
        spec['cbar'].setdefault('fontsize', 8)
    elif not spec['show_cbar_labels']:
        probe = deepcopy(payload)
        probe['show_cbar_labels'] = True
        spec['cbar'] = deepcopy(resolve_payload(probe).get('cbar'))
    spec = PlotSpec.from_dict(spec).to_dict()
    _validate_data({'data': payload.get('data', {})}, path, spec['kind'])
    # Obsolete editor fields live only in the audit snapshot, never alongside
    # the new active configuration where another client could interpret them.
    superseded = {'mode_id', 'compatibility', 'params', 'display', 'show_cbar',
                  'show_cbar_labels', 'cbar_override', 'custom_colors', 'element_overrides'}
    result = {key: deepcopy(value) for key, value in payload.items() if key not in superseded}
    result.update(plot=spec, data=deepcopy(payload.get('data', {})),
                  migration_source=deepcopy(payload))
    fingerprint = hashlib.sha256(_json(payload).encode('utf-8')).hexdigest()
    report['changed_fields'].append(dict(path=f'{path}.plot',
        source_fingerprint=fingerprint, reason='Expanded effective legacy style into explicit PlotSpec'))
    for key in ('plot', 'migration_source'):
        if key in payload:
            report['warnings'].append(dict(path=f'{path}.{key}', code='reserved_field_collision',
                message=f'Existing legacy {key} extension replaced by migration metadata/config; original retained in migration_source.{key}.'))
    report['changed_fields'].append(dict(path=f'{path}.plot.rounding',
        value=spec['rounding'], reason='legacy floating-point rounding is named python'))
    report['warnings'].append(dict(path=f'{path}.plot', code='layout_engine_changed',
        message='The independent renderer uses explicit geometry and margins; historical pixel-identical spacing is not guaranteed.'))
    if payload.get('compatibility'):
        report['warnings'].append(dict(path=path, code='compatibility_parameters',
            message='Only effective legacy parameters are activated; ignored params/display/element overrides remain in migration_source.'))
    if not modern:
        for code, message in (
            ('zero_missing', 'Explicit zero is a measurement; missing values no longer become zero or hide supplied zero.'),
            ('series_labels', 'Lanthanide/actinide labels use correct atomic ranges; historical marker text behavior is removed.'),
        ):
            report['warnings'].append(dict(path=path, code=code, message=message))
    if effective.get('under') is not None:
        report['warnings'].append(dict(path=f'{path}.plot.cmap', code='under_color',
            message='Historical under-range color is not supported by PlotSpec; range/data are unchanged and the old color remains in migration_source.'))
    if spec['layout'] == 'compact':
        report['warnings'].append(dict(path=path, code='compact_hidden_elements',
            message='Compact layout hides series elements; all raw values remain stored.'))
    norm = spec['norm']
    cbar = spec['cbar']
    if cbar and any(t < norm[1] or t > norm[-1] for t in cbar['ticks']):
        report['warnings'].append(dict(path=f'{path}.plot.cbar', code='ticks_outside_range',
            message='Explicit ticks outside the normalization range are retained without correction.'))
    return result


def migrate_document(snapshot):
    """Return {document, report}; validate schema 2 without rewriting it.

    Unsupported preview states anywhere block the entire migration and raise
    MigrationError with all discovered unsupported_fields. Inputs are isolated.
    """
    if not isinstance(snapshot, dict):
        raise ValueError('document must be an object')
    schema = snapshot.get('schema')
    report = dict(source_schema=schema, target_schema=2, changed_fields=[],
                  warnings=[], unsupported_fields=[])
    try:
        _json(snapshot)
        if type(schema) is not int or schema not in (1, 2):
            raise ValueError('document.schema must be 1 or 2')
        if not isinstance(snapshot.get('current'), dict):
            raise ValueError('document.current must be an object')
        if not isinstance(snapshot.get('styles'), dict):
            raise ValueError('document.styles must be an object')
        _validate_excel(snapshot)
        result = deepcopy(snapshot)
        states = [('current', snapshot['current'])] + [
            (f'styles.{name}', value) for name, value in snapshot['styles'].items()]
        for path, payload in states:
            if schema == 2:
                if not isinstance(payload, dict) or not isinstance(payload.get('plot'), dict):
                    raise ValueError(f'{path}.plot must be an object')
                spec = PlotSpec.from_dict(payload['plot']).to_dict()
                _validate_data(payload, path, spec['kind'])
            else:
                migrated = _payload(payload, path, report)
                if path == 'current':
                    result['current'] = migrated
                else:
                    result['styles'][path[len('styles.'):]] = migrated
        if report['unsupported_fields']:
            raise ValueError('Colormap preview states cannot be migrated to PlotSpec')
        result['schema'] = 2
        return dict(document=result, report=report)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise MigrationError(str(exc), report) from exc
