"""Declarative import mapping v1, without workbook or conversion dependencies."""
from dataclasses import dataclass, field

from ._validation import (
    DTO, MAX_ROW, choice, column, coordinate, fields, number, require, string,
)
from .data import _attribute_id


_MAPPING = "MAPPING_INVALID"
_REGION = "REGION_INVALID"
_SHAPE = "MAPPING_SHAPE_MISMATCH"
_TRANSFORM = "TRANSFORM_INVALID"
_POLICIES = {
    "duplicate": "error", "missing": "keep", "hidden": "include", "formula": "cached_only",
}
_LAYOUTS = ("matrix_rows", "matrix_columns", "records", "category_groups")


def _region(data):
    region = fields(data, ("sheet", "range"), name="Region", code=_REGION)
    string(region["sheet"], "sheet", nonempty=True, code=_REGION)
    string(region["range"], "range", code=_REGION)
    ends = region["range"].split(":")
    require(len(ends) <= 2, "Expected one A1 coordinate or a closed range", _REGION)
    top, left = coordinate(ends[0], _REGION)
    bottom, right = coordinate(ends[-1], _REGION)
    require(top <= bottom and left <= right, "Range endpoints must be ordered", _REGION)
    return region, (bottom - top + 1, right - left + 1)


def _regions(layout, data, value_kind):
    if layout in ("matrix_rows", "matrix_columns"):
        names = ("elements", "conditions", "values")
        data = fields(data, names, name="matrix regions", code=_MAPPING)
        dims = {}
        for name in names:
            data[name], dims[name] = _region(data[name])
        require(len({region["sheet"] for region in data.values()}) == 1,
                "Matrix regions must share a sheet", _MAPPING)
        eh, ew = dims["elements"]
        ch, cw = dims["conditions"]
        if layout == "matrix_rows":
            valid = eh == cw == 1 and dims["values"] == (ch, ew)
        else:
            valid = ew == ch == 1 and dims["values"] == (eh, cw)
        require(valid, "Matrix axis and value dimensions do not match", _SHAPE)
    elif layout == "records":
        data = fields(data, ("sheet", "start_row", "end_row", "columns"),
                      name="record regions", code=_MAPPING)
        string(data["sheet"], "sheet", nonempty=True, code=_REGION)
        start, end = data["start_row"], data["end_row"]
        require(type(start) is int and type(end) is int and 1 <= start <= end <= MAX_ROW,
                "Invalid records row bounds", _REGION)
        cols = fields(data["columns"], ("element", "value"), {"condition": None, "attributes": {}},
                      name="record columns", code=_MAPPING)
        used = [column(cols[key], _REGION) for key in ("element", "value")]
        if cols["condition"] is not None:
            used.append(column(cols["condition"], _REGION))
        attrs = cols["attributes"]
        require(type(attrs) is dict, "Attribute columns must be an object", _MAPPING)
        cols["attributes"] = {}
        for key, letter in attrs.items():
            _attribute_id(key, _MAPPING)
            used.append(column(letter, _REGION))
            cols["attributes"][key] = letter
        require(len(used) == len(set(used)), "Record column roles must not overlap", _MAPPING)
        data["columns"] = cols
    else:
        data = fields(data, ("groups",), name="category regions", code=_MAPPING)
        require(value_kind == "category", "Category groups require a category metric", _MAPPING)
        groups = data["groups"]
        require(type(groups) is list and groups, "groups must be a nonempty array", _MAPPING)
        data["groups"] = []
        for group in groups:
            group = fields(group, ("category", "elements"), {"group_name": None},
                           name="category group", code=_MAPPING)
            group["category"], category_dims = _region(group["category"])
            group["elements"], element_dims = _region(group["elements"])
            require(category_dims == (1, 1) and 1 in element_dims,
                    "Expected one category cell and a single element axis", _MAPPING)
            string(group["group_name"], "group_name", nullable=True, code=_MAPPING)
            data["groups"].append(group)
    return data


def _transforms(steps, attrs):
    require(type(steps) is list, "transforms must be an array", _TRANSFORM)
    targets = {"element", "condition", "value"} | {f"attributes.{key}" for key in attrs}
    result = []
    pending_trim = set()
    for index, step in enumerate(steps):
        step = fields(step, ("op", "target", "params"), name="Transform", code=_TRANSFORM)
        op, target = step["op"], step["target"]
        choice(op, ("trim", "case", "numeric_parse", "percent_scale", "round", "aggregate"),
               "transform operation", _TRANSFORM)
        choice(target, targets, "transform target", _TRANSFORM)
        is_key = target in ("element", "condition")
        params = step["params"]
        if op in ("trim", "numeric_parse"):
            params = fields(params, name="transform params", code=_TRANSFORM)
            if op == "trim" and not is_key:
                pending_trim.add(target)
            if op == "numeric_parse":
                require(not is_key, "numeric_parse requires a value or attribute", _TRANSFORM)
                pending_trim.discard(target)
        elif op == "case":
            require(is_key, "case requires element or condition", _TRANSFORM)
            params = fields(params, ("mode",), name="case params", code=_TRANSFORM)
            choice(params["mode"], ("upper", "lower", "element_symbol"), "case mode", _TRANSFORM)
        elif op == "aggregate":
            require(target == "value" and index == len(steps) - 1,
                    "aggregate must target value and be the last step", _TRANSFORM)
            params = fields(params, ("method",), name="aggregate params", code=_TRANSFORM)
            choice(params["method"], ("sum", "mean", "min", "max"), "aggregate method", _TRANSFORM)
        else:
            require(not is_key, f"{op} requires a value or attribute", _TRANSFORM)
            if op == "percent_scale":
                params = fields(params, ("factor",), name="percent_scale params", code=_TRANSFORM)
                number(params["factor"], "factor", _TRANSFORM)
                require(params["factor"] != 0, "factor must be nonzero", _TRANSFORM)
            else:
                params = fields(params, ("digits",), name="round params", code=_TRANSFORM)
                digits = params["digits"]
                require(type(digits) is int and 0 <= digits <= 15, "Invalid round digits", _TRANSFORM)
        step["params"] = params
        result.append(step)
    require(not pending_trim, "Value and attribute trim require subsequent numeric_parse", _TRANSFORM)
    return result


@dataclass(frozen=True)
class ImportMapping(DTO):
    id: str
    source_id: str
    schema_version: int
    layout: str
    regions: dict
    metric: dict
    condition: dict
    policies: dict = field(default_factory=lambda: dict(_POLICIES))
    transforms: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, data):
        data = fields(data, ("id", "source_id", "schema_version", "layout", "regions",
                             "metric", "condition"), {"policies": {}, "transforms": []},
                      name="ImportMapping", code=_MAPPING)
        for key in ("id", "source_id"):
            string(data[key], key, nonempty=True, code=_MAPPING)
        version = data["schema_version"]
        require(type(version) is int, "schema_version must be an integer", _MAPPING)
        require(version == 1, "Unsupported mapping schema version", "SCHEMA_UNSUPPORTED")
        layout = data["layout"]
        choice(layout, _LAYOUTS, "layout", _MAPPING)
        metric = fields(data["metric"], ("name", "value_kind"), {"unit": None},
                        name="metric", code=_MAPPING)
        condition = fields(data["condition"], ("name",), {"unit": None, "interpretation": "literal"},
                           name="condition", code=_MAPPING)
        for descriptor in (metric, condition):
            string(descriptor["name"], "name", nonempty=True, code=_MAPPING)
            string(descriptor["unit"], "unit", nullable=True, code=_MAPPING)
        choice(metric["value_kind"], ("numeric", "text", "category"), "metric value_kind", _MAPPING)
        choice(condition["interpretation"], ("literal", "percent_points", "fraction"),
               "condition interpretation", _MAPPING)
        policies = fields(data["policies"], defaults=_POLICIES, name="policies", code=_MAPPING)
        for key, default in _POLICIES.items():
            allowed = ("include", "exclude") if key == "hidden" else (default,)
            choice(policies[key], allowed, f"{key} policy", _MAPPING)
        regions = _regions(layout, data["regions"], metric["value_kind"])
        attrs = regions["columns"]["attributes"] if layout == "records" else ()
        data.update(metric=metric, condition=condition, policies=policies, regions=regions,
                    transforms=_transforms(data["transforms"], attrs))
        return cls(**data)
