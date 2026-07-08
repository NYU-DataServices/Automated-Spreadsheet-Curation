import re

def _validate_type_error(test_name, arg_name, expected, actual):
    expected_name = (
        expected.__name__
        if isinstance(expected, type)
        else " or ".join(t.__name__ for t in expected)
    )
    actual_name = type(actual).__name__
    raise ValueError(
        f"{test_name}: `{arg_name}` must be {expected_name}, got {actual_name}."
    )


def _validate_kwarg_type(test_name, arg_name, value, expected):
    if not isinstance(value, expected):
        _validate_type_error(test_name, arg_name, expected, value)


def _validate_optional_str_list(test_name, arg_name, value):
    if value is None:
        return []
    if not isinstance(value, list):
        _validate_type_error(test_name, arg_name, list, value)
    bad = [v for v in value if not isinstance(v, str)]
    if bad:
        raise ValueError(
            f"{test_name}: `{arg_name}` must be a list of strings. "
            f"Invalid values: {bad}"
        )
    return value


def _validate_regex_kwarg(test_name, arg_name, pattern):
    _validate_kwarg_type(test_name, arg_name, pattern, str)
    try:
        re.compile(pattern)
    except re.error as e:
        raise ValueError(
            f"{test_name}: `{arg_name}` must be a valid regex pattern. Error: {e}"
        ) from e
    return pattern