from __future__ import annotations

import pytest

from great_expectations.core.expectation_suite import (
    ExpectationSuite,
    SuiteParameterExpressionIssue,
    SuiteParameterReferenceLocation,
)
from great_expectations.core.suite_parameters import (
    extract_suite_parameter_variables,
)

BETWEEN = "expect_column_values_to_be_between"


def _between_kwargs(column: str, **parameterized_kwargs: object) -> dict:
    kwargs: dict = {"column": column}
    kwargs.update(parameterized_kwargs)
    return kwargs


def _suite_with(
    expectations_kwargs: list[dict],
    suite_parameters: dict | None = None,
) -> ExpectationSuite:
    return ExpectationSuite(
        name="test_suite_parameter_check",
        suite_parameters=suite_parameters,
        expectations=[{"type": BETWEEN, "kwargs": kwargs} for kwargs in expectations_kwargs],
    )


# ---------------------------------------------------------------------------
# Static expression variable extraction
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_extract_variables_from_simple_reference():
    result = extract_suite_parameter_variables("my_param")
    assert result.error is None
    assert result.variables == ("my_param",)


@pytest.mark.unit
@pytest.mark.parametrize(
    "expression, expected",
    [
        ("max + 1", ("max",)),
        ("a + b * 2", ("a", "b")),
        ("foo * bar", ("bar", "foo")),
        ("round(foo / 2)", ("foo",)),
        ("trunc(my_value * 0.9)", ("my_value",)),
        ("sin(x) + abs(y)", ("x", "y")),
        ("a + a", ("a",)),
        ("(a + b) * c", ("a", "b", "c")),
    ],
)
def test_extract_variables_from_expressions(expression: str, expected: tuple):
    result = extract_suite_parameter_variables(expression)
    assert result.error is None
    assert result.variables == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "expression",
    [
        "now()",
        "sin(2*PI)",
        "cos(2*pi)",
        "exp(e)",
        "round(3.14)",
        "1 + 1",
        "timedelta(weeks=1)",
        "timedelta(weeks=1, days=2)",
        "now() - timedelta(weeks=1)",
    ],
)
def test_extract_variables_excludes_functions_constants_and_numbers(expression: str):
    result = extract_suite_parameter_variables(expression)
    assert result.error is None
    assert result.variables == ()


@pytest.mark.unit
def test_extract_variables_does_not_treat_keyword_argument_names_as_variables():
    # "weeks"/"days" are keyword argument labels, not suite parameters
    result = extract_suite_parameter_variables("timedelta(weeks=w, days=d)")
    assert result.error is None
    assert result.variables == ("d", "w")


@pytest.mark.unit
def test_extract_variables_bare_function_name_is_a_variable():
    # Without parentheses a function name is parsed as a variable, matching
    # parse_suite_parameter which treats "now" as a missing parameter.
    result = extract_suite_parameter_variables("round")
    assert result.error is None
    assert result.variables == ("round",)


@pytest.mark.unit
@pytest.mark.parametrize(
    "expression",
    [
        "",
        "a + ",
        "2**",
        "foo(a, b=2)",  # mixing positional and keyword arguments is unsupported
        "((",
    ],
)
def test_extract_variables_invalid_expression_is_uncheckable(expression: str):
    result = extract_suite_parameter_variables(expression)
    assert result.variables == ()
    assert result.error is not None
    assert "Parse Failure" in result.error


@pytest.mark.unit
def test_extract_variables_non_string_expression_is_uncheckable():
    result = extract_suite_parameter_variables(123)
    assert result.variables == ()
    assert result.error is not None
    assert "must be a string" in result.error


# ---------------------------------------------------------------------------
# ExpectationSuite.check_suite_parameters
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_check_simple_reference_provided_by_suite():
    suite = _suite_with(
        [_between_kwargs("a", min_value={"$PARAMETER": "min"})],
        suite_parameters={"min": 0},
    )

    result = suite.check_suite_parameters()

    assert result.success is True
    assert result.provided_parameters == ("min",)
    assert result.missing_parameters == ()
    assert result.unused_parameters == ()
    location = SuiteParameterReferenceLocation(
        expectation_index=0,
        expectation_type=BETWEEN,
        kwarg="min_value",
        expression="min",
    )
    assert result.references["min"] == (location,)


@pytest.mark.unit
def test_check_simple_reference_provided_at_runtime():
    suite = _suite_with([_between_kwargs("a", min_value={"$PARAMETER": "min"})])

    result = suite.check_suite_parameters(runtime_parameters={"min": 0})

    assert result.success is True
    assert result.provided_parameters == ("min",)
    assert result.missing_parameters == ()


@pytest.mark.unit
def test_check_missing_parameter_reports_location():
    suite = _suite_with([_between_kwargs("a", max_value={"$PARAMETER": "max"})])

    result = suite.check_suite_parameters()

    assert result.success is False
    assert result.provided_parameters == ()
    assert result.missing_parameters == ("max",)
    locations = result.references["max"]
    assert len(locations) == 1
    assert locations[0].expectation_index == 0
    assert locations[0].expectation_type == BETWEEN
    assert locations[0].kwarg == "max_value"
    assert locations[0].expression == "max"


@pytest.mark.unit
def test_check_expression_extracts_variables_only():
    suite = _suite_with(
        [
            _between_kwargs("a", max_value={"$PARAMETER": "max + 1"}),
            _between_kwargs("b", min_value=0, mostly={"$PARAMETER": "round(pct * 100)"}),
        ],
        suite_parameters={"max": 10, "pct": 0.9},
    )

    result = suite.check_suite_parameters()

    assert result.success is True
    assert result.provided_parameters == ("max", "pct")
    assert result.missing_parameters == ()
    # function names and numeric constants are not treated as parameters
    assert set(result.references) == {"max", "pct"}


@pytest.mark.unit
def test_check_function_only_expressions_need_no_parameters():
    suite = _suite_with(
        [
            _between_kwargs("a", min_value={"$PARAMETER": "now()"}),
            _between_kwargs("b", max_value={"$PARAMETER": "now() - timedelta(weeks=1)"}),
        ]
    )

    result = suite.check_suite_parameters()

    assert result.success is True
    assert result.provided_parameters == ()
    assert result.missing_parameters == ()
    assert result.references == {}


@pytest.mark.unit
def test_check_duplicate_reference_listed_once_with_all_locations():
    suite = _suite_with(
        [
            _between_kwargs("a", min_value={"$PARAMETER": "min"}),
            _between_kwargs("b", min_value={"$PARAMETER": "min"}),
            _between_kwargs("c", max_value={"$PARAMETER": "min + 0"}),
        ],
        suite_parameters={"min": 1},
    )

    result = suite.check_suite_parameters()

    assert result.provided_parameters == ("min",)
    locations = result.references["min"]
    assert [loc.expectation_index for loc in locations] == [0, 1, 2]
    assert [loc.kwarg for loc in locations] == [
        "min_value",
        "min_value",
        "max_value",
    ]


@pytest.mark.unit
def test_check_runtime_parameters_override_suite_parameters():
    suite = _suite_with(
        [_between_kwargs("a", min_value={"$PARAMETER": "min"})],
        suite_parameters={"min": 0},
    )

    result = suite.check_suite_parameters(runtime_parameters={"min": 100})

    assert result.success is True
    assert result.provided_parameters == ("min",)
    assert result.missing_parameters == ()
    # values never appear in the report
    assert "100" not in str(result)


@pytest.mark.unit
def test_check_explicit_none_is_distinguished_from_missing():
    suite = _suite_with(
        [
            _between_kwargs("a", min_value={"$PARAMETER": "none_param"}),
            _between_kwargs("b", min_value={"$PARAMETER": "missing_param"}),
        ],
        suite_parameters={"none_param": None},
    )

    result = suite.check_suite_parameters()

    assert result.provided_parameters == ("none_param",)
    assert result.provided_as_none_parameters == ("none_param",)
    assert result.missing_parameters == ("missing_param",)
    assert result.success is False


@pytest.mark.unit
def test_check_runtime_none_overrides_saved_value_and_is_provided():
    suite = _suite_with(
        [_between_kwargs("a", min_value={"$PARAMETER": "min"})],
        suite_parameters={"min": 0},
    )

    result = suite.check_suite_parameters(runtime_parameters={"min": None})

    assert result.provided_parameters == ("min",)
    assert result.provided_as_none_parameters == ("min",)
    assert result.missing_parameters == ()


@pytest.mark.unit
def test_check_unused_parameters_are_reported():
    suite = _suite_with(
        [_between_kwargs("a", min_value={"$PARAMETER": "min"})],
        suite_parameters={"min": 0, "saved_but_unused": 99},
    )

    result = suite.check_suite_parameters(runtime_parameters={"runtime_unused": "not referenced"})

    assert result.success is True
    assert result.unused_parameters == ("runtime_unused", "saved_but_unused")


@pytest.mark.unit
def test_check_partial_expression_variables():
    suite = _suite_with(
        [_between_kwargs("a", min_value={"$PARAMETER": "a + b"})],
        suite_parameters={"a": 1},
    )

    result = suite.check_suite_parameters()

    assert result.provided_parameters == ("a",)
    assert result.missing_parameters == ("b",)
    assert result.success is False


@pytest.mark.unit
def test_check_invalid_expression_is_marked_unresolvable():
    suite = _suite_with(
        [
            _between_kwargs("a", min_value={"$PARAMETER": "min"}),
            _between_kwargs("b", max_value={"$PARAMETER": "oops +"}),
        ],
        suite_parameters={"min": 0},
    )

    result = suite.check_suite_parameters()

    # a satisfiable parameter elsewhere must not hide the uncheckable expression
    assert result.provided_parameters == ("min",)
    assert result.success is False
    assert len(result.unresolvable_references) == 1
    issue = result.unresolvable_references[0]
    assert isinstance(issue, SuiteParameterExpressionIssue)
    assert issue.expectation_index == 1
    assert issue.kwarg == "max_value"
    assert issue.expression == "oops +"
    assert "Parse Failure" in issue.message
    # the unparseable expression cannot contribute parameter references
    assert "oops" not in result.references


@pytest.mark.unit
def test_check_non_string_expression_is_marked_unresolvable():
    suite = _suite_with(
        [_between_kwargs("a", min_value={"$PARAMETER": 123})],
    )

    result = suite.check_suite_parameters()

    assert result.success is False
    assert len(result.unresolvable_references) == 1
    assert "must be a string" in result.unresolvable_references[0].message


@pytest.mark.unit
def test_check_inline_temporary_value_needs_no_external_parameter():
    suite = _suite_with(
        [{"column": "a", "min_value": {"$PARAMETER": "min", "$PARAMETER.min": -5}}],
    )

    result = suite.check_suite_parameters()

    assert result.success is True
    assert result.missing_parameters == ()
    assert result.references == {}


@pytest.mark.unit
def test_check_does_not_execute_expressions():
    # "1 / 0" would raise at evaluation time; static checking parses without executing.
    suite = _suite_with(
        [_between_kwargs("a", min_value={"$PARAMETER": "1 / 0"})],
    )

    result = suite.check_suite_parameters()

    assert result.success is True
    assert result.references == {}


@pytest.mark.unit
def test_check_empty_suite_reports_all_parameters_unused():
    suite = ExpectationSuite(
        name="empty",
        suite_parameters={"min": 0},
    )

    result = suite.check_suite_parameters(runtime_parameters={"max": 1})

    assert result.success is True
    assert result.provided_parameters == ()
    assert result.missing_parameters == ()
    assert result.unused_parameters == ("max", "min")


@pytest.mark.unit
def test_check_does_not_mutate_suite_or_runtime_mapping():
    suite = _suite_with(
        [_between_kwargs("a", min_value={"$PARAMETER": "min"})],
        suite_parameters={"min": 0},
    )
    runtime_parameters = {"min": 5, "extra": 1}
    suite_parameters_before = dict(suite.suite_parameters)
    runtime_before = dict(runtime_parameters)
    expectation_kwargs_before = dict(suite.expectations[0].configuration.kwargs)

    suite.check_suite_parameters(runtime_parameters=runtime_parameters)

    assert suite.suite_parameters == suite_parameters_before
    assert runtime_parameters == runtime_before
    assert suite.expectations[0].configuration.kwargs == expectation_kwargs_before


@pytest.mark.unit
def test_check_does_not_include_parameter_values_in_result():
    secret = "SUPER-SECRET-VALUE"
    suite = _suite_with(
        [_between_kwargs("a", min_value={"$PARAMETER": "min"})],
        suite_parameters={"min": secret, "unused_secret": secret},
    )

    result = suite.check_suite_parameters(runtime_parameters={"also_secret": secret})

    rendered = str(result)
    assert secret not in rendered
    assert result.provided_parameters == ("min",)
    assert result.unused_parameters == ("also_secret", "unused_secret")
