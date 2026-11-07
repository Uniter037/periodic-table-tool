"""Versioned local JSON interface. No GUI, network service or arbitrary code execution."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

API_VERSION = 1
MAX_JSON_BYTES = 64 * 1024 * 1024
COMMON = {"api_version", "action", "request_id"}
ACTIONS = {
    "describe": set(),
    "create": {"project", "patch"},
    "inspect": {"project"},
    "validate": {"project", "expected_revision", "patch", "dataset_id"},
    "update": {"project", "output_project", "expected_revision", "patch", "dataset_id"},
    "excel_preview": {"workbook", "sheet", "elements_range", "conditions_range", "values_range", "direction"},
    "import_excel": {"project", "output_project", "expected_revision", "workbook", "sheet", "elements_range", "conditions_range", "values_range", "direction", "dataset_index"},
    "export": {"project", "expected_revision", "output_dir", "formats", "base", "allow_out_of_range"},
}
PATCH_FIELDS = {"mode_id", "params", "display", "data", "replace_data", "element_overrides",
                "show_cbar", "show_cbar_labels", "cbar_override", "custom_colors", "compatibility",
                "output_format", "output_dir"}


class ApiError(ValueError):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.details = details


def _path(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ApiError("INVALID_REQUEST", f"{name} must be a nonempty file path")
    return Path(value).expanduser().resolve()


def _fingerprint(raw):
    return hashlib.sha256(raw).hexdigest()


def _read(path):
    with path.open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ApiError("INPUT_TOO_LARGE", "JSON input exceeds 64 MiB")
    return raw


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ApiError("INVALID_JSON", f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _decode(raw):
    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs)
        json.dumps(value, allow_nan=False)
        return value
    except (UnicodeError, ValueError, TypeError) as exc:
        if isinstance(exc, ApiError):
            raise
        raise ApiError("INVALID_JSON", str(exc)) from exc


def _validate_document(document):
    from .project_codec import validate_payload
    from .dataset_collection import DatasetCollection
    if not isinstance(document, dict) or document.get("schema") != 1 or not isinstance(document.get("styles"), dict):
        raise ApiError("INVALID_PROJECT", "Expected a schema=1 .ptproj document")
    validate_payload(document.get("current"))
    for payload in document["styles"].values():
        validate_payload(payload)
    collection = DatasetCollection.from_snapshot(document["excel_collection"]) if "excel_collection" in document else DatasetCollection()
    attached = document.get("excel_attached", False)
    if type(attached) is not bool or (attached and collection.active_dataset_id is None):
        raise ApiError("INVALID_PROJECT", "Invalid Excel group association")
    return collection


def _load(request):
    path = _path(request.get("project"), "project")
    raw = _read(path)
    document = _decode(raw)
    _validate_document(document)
    return path, document, _fingerprint(raw)


def _expect(request, revision, required=True):
    expected = request.get("expected_revision")
    if required and not isinstance(expected, str):
        raise ApiError("REVISION_REQUIRED", "inspect first, then pass expected_revision for project changes")
    if expected is not None and expected != revision:
        raise ApiError("REVISION_CONFLICT", "Project changed; inspect again before applying changes")


def _write_new(path, document):
    """Publish without overwriting existing files, even if another process wins."""
    encoded = (json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".ptable-agent-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise ApiError("OUTPUT_EXISTS", "Output project already exists; choose a new output_project") from exc
    finally:
        Path(temporary).unlink(missing_ok=True)
    return _fingerprint(encoded)


def _save_update(request, path, document, revision):
    from core.document import write_document
    _validate_document(document)
    target = _path(request.get("output_project", str(path)), "output_project")
    if _fingerprint(_read(path)) != revision:
        raise ApiError("REVISION_CONFLICT", "Project changed while preparing the update")
    if target != path:
        return target, _write_new(target, document)
    # A lock serializes cooperating API writers. GUI edits are not live-synchronized.
    lock = path.with_name(path.name + ".agent-lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ApiError("PROJECT_BUSY", "Another API writer holds the project lock") from exc
    try:
        os.close(fd)
        if _fingerprint(_read(path)) != revision:
            raise ApiError("REVISION_CONFLICT", "Project changed before writing")
        write_document(path, document)
        return path, _fingerprint(_read(path))
    finally:
        lock.unlink(missing_ok=True)


def _summary(path, document, revision):
    from .project_codec import resolve_payload
    from core.dataio import convert_data
    from core.scientific import range_warnings
    style = resolve_payload(document["current"])
    values = convert_data(document["current"].get("data", {}), style["kind"])
    return {"project": str(path), "revision": revision, "document": document,
            "resolved_style": style, "warnings": range_warnings(style, values)}


def _patch(document, patch):
    from .project_codec import default_payload, validate_payload
    if not isinstance(patch, dict) or set(patch) - PATCH_FIELDS:
        raise ApiError("INVALID_PATCH", "Unknown patch fields; use describe for supported fields")
    current = copy.deepcopy(document["current"])
    if "mode_id" in patch and patch["mode_id"] != current["mode_id"]:
        document["styles"][current["mode_id"]] = copy.deepcopy(current)
        fresh = default_payload(patch["mode_id"])
        fresh.update(copy.deepcopy(document["styles"].get(patch["mode_id"], {})))
        fresh["data"] = current.get("data", {})
        current = fresh
    if "replace_data" in patch and type(patch["replace_data"]) is not bool:
        raise ApiError("INVALID_PATCH", "replace_data must be a boolean")
    for key, value in patch.items():
        if key == "replace_data":
            continue
        if key in ("params", "display", "data", "element_overrides"):
            if not isinstance(value, dict):
                raise ApiError("INVALID_PATCH", f"{key} must be an object")
            merged = {} if key == "data" and patch.get("replace_data") else copy.deepcopy(current.get(key, {}))
            for name, item in value.items():
                if item is None and key in ("data", "element_overrides"):
                    merged.pop(name, None)
                elif key == "element_overrides" and isinstance(item, dict):
                    merged[name] = {**merged.get(name, {}), **item}
                else:
                    merged[name] = copy.deepcopy(item)
            current[key] = merged
        else:
            current[key] = copy.deepcopy(value)
    if patch.get("replace_data") and "data" not in patch:
        raise ApiError("INVALID_PATCH", "replace_data requires an explicit data object")
    validate_payload(current)
    document["current"] = current
    document["styles"][current["mode_id"]] = copy.deepcopy(current)


def _excel_preview(request):
    from .excel_import import ExcelImportService
    service = ExcelImportService(_path(request.get("workbook"), "workbook"))
    sheet = request.get("sheet")
    if not isinstance(sheet, str):
        return {"sheets": service.sheets, "status": "choose_sheet"}
    return service.preview(sheet, request.get("elements_range", "B1:AG1"),
                           request.get("conditions_range", "A2:A6"),
                           request.get("values_range", "B2:AG6"),
                           request.get("direction", "matrix_rows"))


def _execute(request):
    import matplotlib
    matplotlib.use('Agg')
    from .project_codec import default_payload, resolve_payload
    from .dataset_collection import DatasetCollection
    if not isinstance(request, dict) or type(request.get("api_version")) is not int or request["api_version"] != API_VERSION:
        raise ApiError("API_VERSION", "Request must be an object with api_version=1")
    action = request.get("action")
    if not isinstance(action, str) or action not in ACTIONS:
        raise ApiError("UNKNOWN_ACTION", "Unknown action; call describe")
    unknown = set(request) - COMMON - ACTIONS[action]
    if unknown:
        raise ApiError("INVALID_REQUEST", "Unknown request fields: " + ", ".join(sorted(unknown)))
    if "request_id" in request and not isinstance(request["request_id"], (str, int)):
        raise ApiError("INVALID_REQUEST", "request_id must be a string or integer")
    if action == "describe":
        from core.styles import STYLES
        from .project_codec import PARAM_CHOICES, PARAM_DEFAULTS, DISPLAY_DEFAULTS
        return {"actions": {name: sorted(fields) for name, fields in ACTIONS.items()},
                "parameter_choices": PARAM_CHOICES, "parameter_defaults": PARAM_DEFAULTS,
                "display_defaults": DISPLAY_DEFAULTS,
                "patch_fields": sorted(PATCH_FIELDS), "default_payload": default_payload(),
                "styles": [{"id": key, "name": style["name"], "kind": style["kind"]} for key, style in STYLES.items() if style['kind'] != 'cmap'],
                "concurrency": "Pass inspect.revision as expected_revision. API writers are serialized; close or reload GUI projects when editing externally."}
    if action == "excel_preview":
        return _excel_preview(request)
    if action == "create":
        path = _path(request.get("project"), "project")
        payload = default_payload()
        document = {"schema": 1, "current": payload, "styles": {},
                    "excel_collection": DatasetCollection().snapshot(), "excel_attached": False}
        _patch(document, request.get("patch", {}))
        revision = _write_new(path, document)
        return _summary(path, document, revision)
    path, document, revision = _load(request)
    if action == "inspect":
        return _summary(path, document, revision)
    _expect(request, revision, required=action not in ("export", "validate"))
    if action in ("update", "import_excel", "validate"):
        collection = _validate_document(document)
        if document.get("excel_attached"):
            collection.set_manual_data(document["current"].get("data", {}))
        details = {}
        if action == "import_excel":
            preview = _excel_preview(request)
            if preview["status"] != "ready":
                raise ApiError("EXCEL_INVALID", "Excel selection is not ready; inspect error.details", preview)
            index = request.get("dataset_index", 0)
            if type(index) is not int or not 0 <= index < len(preview['datasets']):
                raise ApiError("INVALID_REQUEST", "dataset_index must identify one of the imported groups")
            ids = collection.append(preview)
            collection.select(ids[index])
            document["excel_attached"] = True
            document['current']['data'] = collection.effective_data()
            details = {"import_stats": preview['stats'], "dataset_ids": ids}
        elif "dataset_id" in request:
            collection.select(request["dataset_id"])
            document["excel_attached"] = True
            document['current']['data'] = collection.effective_data()
        _patch(document, request.get("patch", {}))
        if document.get('excel_attached'):
            collection.set_manual_data(document['current']['data'])
        document['excel_collection'] = collection.snapshot()
        if action == 'validate':
            result = _summary(path, document, revision)
            result['base_revision'] = result.pop('revision')
            return {**result, 'dry_run':True}
        target, new_revision = _save_update(request, path, document, revision)
        return {**_summary(target, document, new_revision), **details}
    if action == "export":
        from core.styles import render_table
        from core.scientific import range_warnings
        from core.dataio import convert_data
        from core.imaging import save_options
        from core.saver import save_figure
        import matplotlib.pyplot as plt
        payload = document['current']
        style = resolve_payload(payload)
        data = convert_data(payload.get('data', {}), style['kind'])
        if not data:
            raise ApiError("EMPTY_DATA", "Project has no plot data")
        formats = request.get("formats", [payload.get('output_format', 'svg')])
        if not isinstance(formats, list) or not formats or any(f not in ('png','svg','pdf') for f in formats) or len(set(formats)) != len(formats):
            raise ApiError("INVALID_REQUEST", "formats must be a nonempty unique list of png/svg/pdf")
        base = request.get("base", "periodic_table")
        if not isinstance(base, str) or not re.fullmatch(r"[\w-]{1,80}", base):
            raise ApiError("INVALID_REQUEST", "base must be 1–80 letters/digits/underscores/hyphens")
        warnings = range_warnings(style, data)
        allow = request.get('allow_out_of_range', False)
        if type(allow) is not bool:
            raise ApiError('INVALID_REQUEST', 'allow_out_of_range must be boolean')
        if warnings and not allow:
            raise ApiError('RANGE_WARNING', '; '.join(warnings) + '; set allow_out_of_range=true to acknowledge')
        directory = _path(request.get('output_dir', payload.get('output_dir') or 'output'), 'output_dir')
        figsize = style.get('figsize', (10,5))
        if figsize[0]*figsize[1]*style.get('dpi',100)**2 > 64_000_000:
            raise ApiError('OUTPUT_TOO_LARGE', 'Requested canvas exceeds 64 million pixels')
        fig = render_table(style, data, title=payload.get('params',{}).get('title') if style.get('customizable') else None,
                           show_cbar=payload.get('show_cbar',True), figsize=figsize)
        paths = []
        try:
            for fmt in formats:
                paths.append(Path(save_figure(fig,str(directory),base,fmt,**save_options(style))))
            return {'project':str(path), 'revision':revision,'warnings':warnings,
                    'files':[{'path':str(p),'bytes':p.stat().st_size,'sha256':_fingerprint(p.read_bytes())} for p in paths]}
        except Exception:
            for p in paths:
                p.unlink(missing_ok=True)
            raise
        finally:
            plt.close(fig)
    raise ApiError('UNKNOWN_ACTION', action)


def execute(request):
    """Execute one JSON-serializable request, returning a JSON response envelope."""
    response = {'api_version': API_VERSION}
    if isinstance(request, dict) and isinstance(request.get('request_id'), (str,int)):
        response['request_id'] = request['request_id']
    try:
        json.dumps(request, allow_nan=False)
        response.update(ok=True, result=_execute(copy.deepcopy(request)))
    except ApiError as exc:
        response.update(ok=False, error={'code':exc.code,'message':str(exc)})
        if exc.details is not None:
            response['error']['details'] = exc.details
    except (ValueError,TypeError,KeyError) as exc:
        response.update(ok=False,error={'code':'VALIDATION_ERROR','message':str(exc)})
    except OSError as exc:
        response.update(ok=False,error={'code':'IO_ERROR','message':str(exc)})
    except Exception as exc:
        response.update(ok=False,error={'code':'INTERNAL_ERROR','message':str(exc)})
    return response


def main(argv=None):
    import matplotlib
    matplotlib.use('Agg')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request','--agent-request',dest='request',required=True,help='UTF-8 JSON request file; - reads stdin')
    parser.add_argument('--response','--agent-response',dest='response',help='UTF-8 JSON response file (required for windowed EXE)')
    args=parser.parse_args(argv)
    try:
        if args.request == '-':
            if sys.stdin is None:
                raise ApiError('INVALID_REQUEST','No stdin; use a request file')
            raw=sys.stdin.buffer.read(MAX_JSON_BYTES+1)
        else:
            raw=_read(_path(args.request,'request'))
        if len(raw)>MAX_JSON_BYTES:
            raise ApiError('INPUT_TOO_LARGE','JSON input exceeds 64 MiB')
        request=_decode(raw)
        if args.response:
            response_path=_path(args.response,'response')
            protected=[args.request] if args.request!='-' else []
            if isinstance(request,dict):
                protected += [request[k] for k in ('project','output_project','workbook') if isinstance(request.get(k),str)]
            if any(response_path==_path(p,'input') for p in protected):
                raise ApiError('PATH_CONFLICT','Response path must differ from requests, projects and workbooks')
        elif sys.stdout is None:
            raise ApiError('INVALID_REQUEST','Windowed EXE requires --response')
        response=execute(request)
    except (ApiError,OSError,ValueError) as exc:
        response={'api_version':1,'ok':False,'error':{'code':getattr(exc,'code','INVALID_REQUEST'),'message':str(exc)}}
        if getattr(exc,'code',None)=='PATH_CONFLICT':
            args.response=None
    if args.response:
        from core.document import write_document
        write_document(_path(args.response,'response'),response)
    elif sys.stdout is not None:
        if hasattr(sys.stdout,'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        print(json.dumps(response,ensure_ascii=False,allow_nan=False))
    return 0 if response['ok'] else 2


if __name__=='__main__':
    raise SystemExit(main())
