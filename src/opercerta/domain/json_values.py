import math


def require_json_object(value: object, field_name: str) -> object:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    _require_json_value(value, field_name)
    return value


def _require_json_value(value: object, field_name: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} numbers must be finite")
        return
    if isinstance(value, list):
        for item in value:
            _require_json_value(item, field_name)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{field_name} object keys must be strings")
            _require_json_value(item, field_name)
        return
    raise ValueError(f"{field_name} must contain only JSON values")
