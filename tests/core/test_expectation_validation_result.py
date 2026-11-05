from __future__ import annotations

import json
from dataclasses import fields
from typing import Any, cast

import pandas as pd
import pytest

import great_expectations.expectations as gxe
from great_expectations.core import (
    ExpectationResultComparison,
    ExpectationResultComparisonCategory,
    ExpectationSuiteValidationResult,
    ExpectationSuiteValidationResultComparison,
    ExpectationValidationResult,
    compare_suite_validation_results,
)
from great_expectations.core.batch import BatchMarkers, LegacyBatchDefinition
from great_expectations.core.expectation_validation_result import (
    ExpectationSuiteValidationResultMeta,
)
from great_expectations.core.id_dict import BatchSpec, IDDict
from great_expectations.core.run_identifier import RunIdentifier
from great_expectations.exceptions import (
    ExpectationSuiteValidationResultComparisonError,
)
from great_expectations.expectations.expectation_configuration import (
    ExpectationConfiguration,
)
from great_expectations.expectations.metadata_types import FailureSeverity


@pytest.mark.unit
def test_expectation_validation_result_describe_returns_expected_description():
    # arrange
    evr = ExpectationValidationResult(
        success=False,
        expectation_config=gxe.ExpectColumnValuesToBeBetween(
            column="passenger_count",
            min_value=0,
            max_value=6,
            notes="Per the TLC data dictionary, this is a driver-submitted value (historically between 0 to 6)",  # noqa: E501 # FIXME CoP
        ).configuration,
        result={
            "element_count": 100000,
            "unexpected_count": 1,
            "unexpected_percent": 0.001,
            "partial_unexpected_list": [7.0],
            "missing_count": 0,
            "missing_percent": 0.0,
            "unexpected_percent_total": 0.001,
            "unexpected_percent_nonmissing": 0.001,
            "partial_unexpected_counts": [{"value": 7.0, "count": 1}],
            "partial_unexpected_index_list": [48422],
        },
        exception_info={
            "raised_exception": False,
            "exception_traceback": None,
            "exception_message": None,
        },
    )
    # act
    description = evr.describe()
    # assert
    assert description == json.dumps(
        {
            "expectation_type": "expect_column_values_to_be_between",
            "success": False,
            "kwargs": {"column": "passenger_count", "min_value": 0.0, "max_value": 6.0},
            "result": {
                "element_count": 100000,
                "unexpected_count": 1,
                "unexpected_percent": 0.001,
                "partial_unexpected_list": [7.0],
                "missing_count": 0,
                "missing_percent": 0.0,
                "unexpected_percent_total": 0.001,
                "unexpected_percent_nonmissing": 0.001,
                "partial_unexpected_counts": [{"value": 7.0, "count": 1}],
                "partial_unexpected_index_list": [48422],
            },
        },
        indent=4,
    )


@pytest.mark.unit
def test_expectation_validation_result_describe_returns_expected_description_with_null_values():
    # It's unclear if an ExpectationValidationResult can ever be valid without an Expectation
    # or a result, but since it's typed that way we test it
    # arrange
    evr = ExpectationValidationResult(
        success=True,
        exception_info={
            "raised_exception": False,
            "exception_traceback": None,
            "exception_message": None,
        },
    )
    # act
    description = evr.describe()
    # assert
    assert description == json.dumps(
        {
            "expectation_type": None,
            "success": True,
            "kwargs": None,
            "result": {},
        },
        indent=4,
    )


@pytest.mark.unit
def test_expectation_validation_result_describe_returns_expected_description_with_exception():
    # arrange
    evr = ExpectationValidationResult(
        success=False,
        expectation_config=gxe.ExpectColumnValuesToBeBetween(
            column="passenger_count",
            min_value=0,
            max_value=6,
            notes="Per the TLC data dictionary, this is a driver-submitted value (historically between 0 to 6)",  # noqa: E501 # FIXME CoP
        ).configuration,
        result={
            "element_count": 100000,
            "unexpected_count": 1,
            "unexpected_percent": 0.001,
            "partial_unexpected_list": [7.0],
            "missing_count": 0,
            "missing_percent": 0.0,
            "unexpected_percent_total": 0.001,
            "unexpected_percent_nonmissing": 0.001,
            "partial_unexpected_counts": [{"value": 7.0, "count": 1}],
            "partial_unexpected_index_list": [48422],
        },
        exception_info={
            "raised_exception": True,
            "exception_traceback": "Traceback (most recent call last): something went wrong",
            "exception_message": "Helpful message here",
        },
    )
    # act
    description = evr.describe()
    # assert
    assert description == json.dumps(
        {
            "expectation_type": "expect_column_values_to_be_between",
            "success": False,
            "kwargs": {"column": "passenger_count", "min_value": 0.0, "max_value": 6.0},
            "result": {
                "element_count": 100000,
                "unexpected_count": 1,
                "unexpected_percent": 0.001,
                "partial_unexpected_list": [7.0],
                "missing_count": 0,
                "missing_percent": 0.0,
                "unexpected_percent_total": 0.001,
                "unexpected_percent_nonmissing": 0.001,
                "partial_unexpected_counts": [{"value": 7.0, "count": 1}],
                "partial_unexpected_index_list": [48422],
            },
            "exception_info": {
                "raised_exception": True,
                "exception_traceback": "Traceback (most recent call last): something went wrong",
                "exception_message": "Helpful message here",
            },
        },
        indent=4,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "validation_result_url",
    [
        "https://app.greatexpectations.io/organizations/my-org/data-assets/6f6d390b-a52b-41d1-b5c0-a1d57a6b4618/validations/expectation-suites/a0af0eb5-90ab-4219-ab60-482eee0a8b32/results/e77ce5e4-b71b-4f86-9c3b-f82385aab660",
        None,
    ],
)
def test_expectation_suite_validation_result_returns_expected_shape(
    validation_result_url: str | None,
):
    # arrange
    svr = ExpectationSuiteValidationResult(
        success=True,
        statistics={
            "evaluated_expectations": 2,
            "successful_expectations": 2,
            "unsuccessful_expectations": 0,
            "success_percent": 100.0,
        },
        suite_name="empty_suite",
        results=[
            ExpectationValidationResult(
                meta={},
                success=True,
                exception_info={
                    "raised_exception": False,
                    "exception_traceback": None,
                    "exception_message": None,
                },
                result={
                    "element_count": 100000,
                    "unexpected_count": 1,
                    "unexpected_percent": 0.001,
                    "partial_unexpected_list": [7.0],
                    "missing_count": 0,
                    "missing_percent": 0.0,
                    "unexpected_percent_total": 0.001,
                    "unexpected_percent_nonmissing": 0.001,
                    "partial_unexpected_counts": [{"value": 7.0, "count": 1}],
                    "partial_unexpected_index_list": [48422],
                },
                expectation_config=ExpectationConfiguration(
                    meta={},
                    notes="Per the TLC data dictionary, this is a driver-submitted value (historically between 0 to 6)",  # noqa: E501 # FIXME CoP
                    id="9f76d0b5-9d99-4ed9-a269-339b35e60490",
                    kwargs={
                        "batch_id": "default_pandas_datasource-#ephemeral_pandas_asset",
                        "mostly": 0.95,
                        "column": "passenger_count",
                        "min_value": 0.0,
                        "max_value": 6.0,
                    },
                    type="expect_column_values_to_be_between",
                ),
            ),
            ExpectationValidationResult(
                meta={},
                success=True,
                exception_info={
                    "raised_exception": False,
                    "exception_traceback": None,
                    "exception_message": None,
                },
                result={
                    "element_count": 100000,
                    "unexpected_count": 0,
                    "unexpected_percent": 0.0,
                    "partial_unexpected_list": [],
                    "partial_unexpected_counts": [],
                    "partial_unexpected_index_list": [],
                },
                expectation_config=ExpectationConfiguration(
                    meta={},
                    id="19c0e80c-d676-4b01-a4a3-2a568552d368",
                    kwargs={
                        "batch_id": "default_pandas_datasource-#ephemeral_pandas_asset",
                        "column": "trip_distance",
                    },
                    type="expect_column_values_to_not_be_null",
                ),
            ),
        ],
        result_url=validation_result_url,
    )
    # act
    description = svr.describe()
    # assert
    assert description == json.dumps(
        {
            "success": True,
            "statistics": {
                "evaluated_expectations": 2,
                "successful_expectations": 2,
                "unsuccessful_expectations": 0,
                "success_percent": 100.0,
            },
            "expectations": [
                {
                    "expectation_type": "expect_column_values_to_be_between",
                    "success": True,
                    "kwargs": {
                        "batch_id": "default_pandas_datasource-#ephemeral_pandas_asset",
                        "mostly": 0.95,
                        "column": "passenger_count",
                        "min_value": 0.0,
                        "max_value": 6.0,
                    },
                    "result": {
                        "element_count": 100000,
                        "unexpected_count": 1,
                        "unexpected_percent": 0.001,
                        "partial_unexpected_list": [7.0],
                        "missing_count": 0,
                        "missing_percent": 0.0,
                        "unexpected_percent_total": 0.001,
                        "unexpected_percent_nonmissing": 0.001,
                        "partial_unexpected_counts": [{"value": 7.0, "count": 1}],
                        "partial_unexpected_index_list": [48422],
                    },
                },
                {
                    "expectation_type": "expect_column_values_to_not_be_null",
                    "success": True,
                    "kwargs": {
                        "batch_id": "default_pandas_datasource-#ephemeral_pandas_asset",
                        "column": "trip_distance",
                    },
                    "result": {
                        "element_count": 100000,
                        "unexpected_count": 0,
                        "unexpected_percent": 0.0,
                        "partial_unexpected_list": [],
                        "partial_unexpected_counts": [],
                        "partial_unexpected_index_list": [],
                    },
                },
            ],
            "result_url": validation_result_url,
        },
        indent=4,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "validation_result_url",
    [
        "https://app.greatexpectations.io/organizations/my-org/data-assets/6f6d390b-a52b-41d1-b5c0-a1d57a6b4618/validations/expectation-suites/a0af0eb5-90ab-4219-ab60-482eee0a8b32/results/e77ce5e4-b71b-4f86-9c3b-f82385aab660",
        None,
    ],
)
def test_expectation_suite_validation_asset_name_access(
    validation_result_url: str | None,
):
    # arrange
    svr = ExpectationSuiteValidationResult(
        meta=ExpectationSuiteValidationResultMeta(
            active_batch_definition=LegacyBatchDefinition(
                batch_identifiers=IDDict({}),
                data_asset_name="taxi_data_1.csv",
                data_connector_name="default_inferred_data_connector_name",
                datasource_name="pandas",
            ),
            batch_markers=BatchMarkers(
                {
                    "ge_load_time": "20220727T154327.630107Z",
                    "pandas_data_fingerprint": "c4f929e6d4fab001fedc9e075bf4b612",
                }
            ),
            batch_spec=BatchSpec({"path": "../data/taxi_data_1.csv"}),
            checkpoint_name="single_validation_checkpoint",
            expectation_suite_name="taxi_suite_1",
            great_expectations_version="0.15.15",
            run_id=RunIdentifier(
                run_name="20220727-114327-my-run-name-template",
                run_time="2022-07-27T11:43:27.625252+00:00",
            ),
            validation_time="20220727T154327.701100Z",
            batch_parameters=None,
            checkpoint_id=None,
            validation_id=None,
        ),
        success=True,
        statistics={
            "evaluated_expectations": 2,
            "successful_expectations": 2,
            "unsuccessful_expectations": 0,
            "success_percent": 100.0,
        },
        suite_name="empty_suite",
        results=[
            ExpectationValidationResult(
                meta={},
                success=True,
                exception_info={
                    "raised_exception": False,
                    "exception_traceback": None,
                    "exception_message": None,
                },
                result={
                    "element_count": 100000,
                    "unexpected_count": 1,
                    "unexpected_percent": 0.001,
                    "partial_unexpected_list": [7.0],
                    "missing_count": 0,
                    "missing_percent": 0.0,
                    "unexpected_percent_total": 0.001,
                    "unexpected_percent_nonmissing": 0.001,
                    "partial_unexpected_counts": [{"value": 7.0, "count": 1}],
                    "partial_unexpected_index_list": [48422],
                },
                expectation_config=ExpectationConfiguration(
                    meta={},
                    notes="Test notes",
                    id="9f76d0b5-9d99-4ed9-a269-339b35e60490",
                    kwargs={
                        "batch_id": "default_pandas_datasource-#ephemeral_pandas_asset",
                    },
                    type="expect_column_values_to_be_between",
                ),
            ),
        ],
        result_url=validation_result_url,
    )

    assert svr.asset_name == "taxi_data_1.csv"


@pytest.mark.unit
def test_render_updates_rendered_content():
    evr = ExpectationValidationResult(
        success=False,
        expectation_config=gxe.ExpectColumnValuesToBeBetween(
            column="passenger_count",
            min_value=0,
            max_value=6,
            notes="Per the TLC data dictionary, this is a driver-submitted value (historically between 0 to 6)",  # noqa: E501 # FIXME CoP
        ).configuration,
        result={
            "element_count": 100000,
            "unexpected_count": 1,
            "unexpected_percent": 0.001,
            "partial_unexpected_list": [7.0],
            "missing_count": 0,
            "missing_percent": 0.0,
            "unexpected_percent_total": 0.001,
            "unexpected_percent_nonmissing": 0.001,
            "partial_unexpected_counts": [{"value": 7.0, "count": 1}],
            "partial_unexpected_index_list": [48422],
        },
    )

    assert evr.rendered_content is None

    evr.render()

    assert evr.rendered_content is not None


@pytest.mark.unit
@pytest.mark.parametrize(
    "severity_enum,expected_string",
    [
        (FailureSeverity.WARNING, "warning"),
        (FailureSeverity.CRITICAL, "critical"),
        (FailureSeverity.INFO, "info"),
    ],
)
def test_expectation_validation_result_with_severity_enum_serializes_properly(
    severity_enum, expected_string
):
    """Test that expectation validation results with severity enums serialize without errors."""

    # Create an expectation config with severity enum at top level
    config = ExpectationConfiguration(
        type="expect_table_row_count_to_be_between",
        kwargs={"min_value": 0, "max_value": 100},
        severity=severity_enum,
    )

    evr = ExpectationValidationResult(
        success=True,
        expectation_config=config,
        result={
            "observed_value": 50,
            "element_count": 1000,
            "missing_count": 0,
            "missing_percent": 0.0,
        },
        exception_info={
            "raised_exception": False,
            "exception_traceback": None,
            "exception_message": None,
        },
    )

    # Test that the validation result serializes without errors and severity is correct
    json_dict = evr.to_json_dict()
    # Verify the severity was converted to the expected string value
    assert json_dict["expectation_config"]["severity"] == expected_string


class TestSerialization:
    @pytest.mark.unit
    def test_expectation_validation_results_serializes(self) -> None:
        evr = ExpectationValidationResult(
            success=True,
            expectation_config=gxe.ExpectColumnDistinctValuesToEqualSet(
                column="passenger_count",
                value_set=[1, 2],
            ).configuration,
            result={
                "details": {
                    "observed_value": pd.Series({"a": 1, "b": 2, "c": 4}),
                }
            },
        )

        # Ensure the results are serializable.
        as_dict = evr.describe_dict()
        from_describe_dict = json.dumps(as_dict, indent=4)
        from_describe = evr.describe()

        assert from_describe_dict == from_describe
        assert as_dict["result"]["details"]["observed_value"] == [
            {"index": "a", "value": 1},
            {"index": "b", "value": 2},
            {"index": "c", "value": 4},
        ]

    @pytest.mark.unit
    def test_expectation_suite_validation_results_serializes(self) -> None:
        svr = ExpectationSuiteValidationResult(
            success=True,
            statistics={
                "evaluated_expectations": 2,
                "successful_expectations": 2,
                "unsuccessful_expectations": 0,
                "success_percent": 100.0,
            },
            suite_name="whatever",
            results=[
                ExpectationValidationResult(
                    success=True,
                    expectation_config=gxe.ExpectColumnDistinctValuesToEqualSet(
                        column="passenger_count",
                        value_set=[1, 2],
                    ).configuration,
                    result={
                        "details": {
                            "observed_value": pd.Series({"a": 1, "b": 2, "c": 4}),
                        }
                    },
                )
            ],
        )

        # Ensure the results are serializable.
        as_dict = svr.describe_dict()
        from_describe_dict = json.dumps(as_dict, indent=4)
        from_describe = svr.describe()

        assert from_describe_dict == from_describe
        assert as_dict["expectations"][0]["result"]["details"]["observed_value"] == [
            {"index": "a", "value": 1},
            {"index": "b", "value": 2},
            {"index": "c", "value": 4},
        ]


class TestExpectationValidationResultHash:
    @pytest.mark.unit
    def test_hash_consistency_with_equality(self):
        config1 = ExpectationConfiguration(
            type="expect_column_values_to_not_be_null", kwargs={"column": "test_column"}
        )
        config2 = ExpectationConfiguration(
            type="expect_column_values_to_not_be_null", kwargs={"column": "test_column"}
        )

        result1 = ExpectationValidationResult(
            success=True,
            expectation_config=config1,
            result={"observed_value": 100},
            meta={"test": "value"},
            exception_info={"raised_exception": False},
        )

        result2 = ExpectationValidationResult(
            success=True,
            expectation_config=config2,
            result={"observed_value": 100},
            meta={"test": "value"},
            exception_info={"raised_exception": False},
        )

        assert result1 == result2
        assert hash(result1) == hash(result2)

    @pytest.mark.unit
    def test_hash_different_for_different_success(self):
        config = ExpectationConfiguration(
            type="expect_column_values_to_not_be_null", kwargs={"column": "test_column"}
        )

        result1 = ExpectationValidationResult(
            success=True, expectation_config=config, result={"observed_value": 100}
        )

        result2 = ExpectationValidationResult(
            success=False, expectation_config=config, result={"observed_value": 100}
        )

        assert result1 != result2
        assert hash(result1) != hash(result2)

    @pytest.mark.unit
    def test_hash_different_for_different_results(self):
        config = ExpectationConfiguration(
            type="expect_column_values_to_not_be_null", kwargs={"column": "test_column"}
        )

        result1 = ExpectationValidationResult(
            success=True, expectation_config=config, result={"observed_value": 100}
        )

        result2 = ExpectationValidationResult(
            success=True, expectation_config=config, result={"observed_value": 200}
        )

        assert result1 != result2
        assert hash(result1) != hash(result2)

    @pytest.mark.unit
    def test_hash_stable_across_runs(self):
        config = ExpectationConfiguration(
            type="expect_column_values_to_not_be_null", kwargs={"column": "test_column"}
        )

        result = ExpectationValidationResult(
            success=True,
            expectation_config=config,
            result={"observed_value": 100},
            meta={"test": "value"},
            exception_info={"raised_exception": False},
        )

        hash1 = hash(result)
        hash2 = hash(result)
        hash3 = hash(result)

        assert hash1 == hash2 == hash3


class TestExpectationSuiteValidationResultHash:
    @pytest.mark.unit
    def test_hash_consistency_with_equality(self):
        config = ExpectationConfiguration(
            type="expect_column_values_to_not_be_null", kwargs={"column": "test_column"}
        )

        evr = ExpectationValidationResult(
            success=True, expectation_config=config, result={"observed_value": 100}
        )

        result1 = ExpectationSuiteValidationResult(
            suite_name="test_suite",
            success=True,
            results=[evr],
            suite_parameters={"param": "value"},
            statistics={"evaluated_expectations": 1},
            meta={"test": "value"},
        )

        result2 = ExpectationSuiteValidationResult(
            suite_name="test_suite",
            success=True,
            results=[evr],
            suite_parameters={"param": "value"},
            statistics={"evaluated_expectations": 1},
            meta={"test": "value"},
        )

        assert result1 == result2
        assert hash(result1) == hash(result2)

    @pytest.mark.unit
    def test_hash_different_for_different_success(self):
        config = ExpectationConfiguration(
            type="expect_column_values_to_not_be_null", kwargs={"column": "test_column"}
        )

        evr = ExpectationValidationResult(
            success=True, expectation_config=config, result={"observed_value": 100}
        )

        result1 = ExpectationSuiteValidationResult(
            suite_name="test_suite",
            success=True,
            results=[evr],
            suite_parameters={"param": "value"},
        )

        result2 = ExpectationSuiteValidationResult(
            suite_name="test_suite",
            success=False,
            results=[evr],
            suite_parameters={"param": "value"},
        )

        assert result1 != result2
        assert hash(result1) != hash(result2)

    @pytest.mark.unit
    def test_hash_stable_across_runs(self):
        config = ExpectationConfiguration(
            type="expect_column_values_to_not_be_null", kwargs={"column": "test_column"}
        )

        evr = ExpectationValidationResult(
            success=True, expectation_config=config, result={"observed_value": 100}
        )

        result = ExpectationSuiteValidationResult(
            suite_name="test_suite",
            success=True,
            results=[evr],
            suite_parameters={"param": "value"},
            statistics={"evaluated_expectations": 1},
            meta={"test": "value"},
        )

        hash1 = hash(result)
        hash2 = hash(result)
        hash3 = hash(result)

        assert hash1 == hash2 == hash3


class TestExpectationProperty:
    @pytest.mark.unit
    def test_returns_typed_expectation_from_config(self):
        config = ExpectationConfiguration(
            type="expect_column_values_to_not_be_null",
            kwargs={"column": "foo"},
        )
        evr = ExpectationValidationResult(
            success=True,
            expectation_config=config,
        )
        expectation = evr.expectation
        assert isinstance(expectation, gxe.ExpectColumnValuesToNotBeNull)
        assert expectation.column == "foo"

    @pytest.mark.unit
    def test_works_for_unexpected_rows_expectation(self):
        config = ExpectationConfiguration(
            type="unexpected_rows_expectation",
            kwargs={"unexpected_rows_query": "SELECT * FROM {batch} WHERE col > 5"},
        )
        evr = ExpectationValidationResult(
            success=False,
            expectation_config=config,
        )
        expectation = evr.expectation
        assert isinstance(expectation, gxe.UnexpectedRowsExpectation)
        assert expectation.unexpected_rows_query == "SELECT * FROM {batch} WHERE col > 5"


class TestBatchParametersProperty:
    @pytest.mark.unit
    def test_returns_batch_parameters_from_meta(self):
        params = {"year": 2026, "month": 3}
        esvr = ExpectationSuiteValidationResult(
            success=True,
            results=[],
            suite_name="test_suite",
            meta={"batch_parameters": params},
        )
        assert esvr.batch_parameters == params

    @pytest.mark.unit
    def test_returns_none_when_missing(self):
        esvr = ExpectationSuiteValidationResult(
            success=True,
            results=[],
            suite_name="test_suite",
            meta={},
        )
        assert esvr.batch_parameters is None


class TestGetMaxSeverityFailure:
    @pytest.mark.unit
    def test_get_max_severity_failure_no_results(self):
        """Test that None is returned when there are no results."""
        result = ExpectationSuiteValidationResult(
            suite_name="test_suite",
            success=True,
            results=[],
        )

        assert result.get_max_severity_failure() is None

    @pytest.mark.unit
    def test_get_max_severity_failure_no_failures(self):
        """Test that None is returned when all expectations pass."""
        config = ExpectationConfiguration(
            type="expect_column_values_to_not_be_null",
            kwargs={"column": "test_column"},
            severity="critical",
        )

        evr = ExpectationValidationResult(
            success=True, expectation_config=config, result={"observed_value": 100}
        )

        result = ExpectationSuiteValidationResult(
            suite_name="test_suite",
            success=True,
            results=[evr],
        )

        assert result.get_max_severity_failure() is None

    @pytest.mark.unit
    def test_get_max_severity_failure_multiple_failures(self):
        """Test that the highest severity is returned among multiple failures."""

        config1 = ExpectationConfiguration(
            type="expect_column_values_to_not_be_null",
            kwargs={"column": "test_column"},
            severity="info",
        )
        config2 = ExpectationConfiguration(
            type="expect_column_values_to_be_between",
            kwargs={
                "column": "test_column",
                "min_value": 0,
                "max_value": 100,
            },
            severity="warning",
        )
        config3 = ExpectationConfiguration(
            type="expect_column_values_to_be_unique",
            kwargs={"column": "test_column"},
            severity="critical",
        )

        evr1 = ExpectationValidationResult(success=False, expectation_config=config1, result={})
        evr2 = ExpectationValidationResult(success=False, expectation_config=config2, result={})
        evr3 = ExpectationValidationResult(success=False, expectation_config=config3, result={})

        result = ExpectationSuiteValidationResult(
            suite_name="test_suite",
            success=False,
            results=[evr1, evr2, evr3],
        )

        assert result.get_max_severity_failure() == FailureSeverity.CRITICAL

    @pytest.mark.unit
    def test_get_max_severity_failure_mixed_success_failure(self):
        """Test that only failed expectations are considered."""

        config1 = ExpectationConfiguration(
            type="expect_column_values_to_not_be_null",
            kwargs={"column": "test_column"},
            severity="critical",
        )
        config2 = ExpectationConfiguration(
            type="expect_column_values_to_be_between",
            kwargs={
                "column": "test_column",
                "min_value": 0,
                "max_value": 100,
            },
            severity="warning",
        )

        evr1 = ExpectationValidationResult(success=True, expectation_config=config1, result={})
        evr2 = ExpectationValidationResult(success=False, expectation_config=config2, result={})

        result = ExpectationSuiteValidationResult(
            suite_name="test_suite",
            success=False,
            results=[evr1, evr2],
        )

        assert result.get_max_severity_failure() == FailureSeverity.WARNING

    @pytest.mark.unit
    def test_failure_severity_enum_semantic_ordering(self):
        """Test that FailureSeverity enum values sort semantically."""
        from great_expectations.expectations.metadata_types import FailureSeverity

        # Test that the enum values sort in semantic order (info < warning < critical)
        # This should NOT depend on lexicographical order of the string values
        severity_values = [FailureSeverity.CRITICAL, FailureSeverity.WARNING, FailureSeverity.INFO]

        # Sort the values - they should now be in the correct semantic order
        sorted_severities = sorted(severity_values)

        # Verify the semantic order: info < warning < critical
        assert sorted_severities[0] == FailureSeverity.INFO, (
            f"Expected INFO first, got {sorted_severities[0]}"
        )
        assert sorted_severities[1] == FailureSeverity.WARNING, (
            f"Expected WARNING second, got {sorted_severities[1]}"
        )
        assert sorted_severities[2] == FailureSeverity.CRITICAL, (
            f"Expected CRITICAL third, got {sorted_severities[2]}"
        )

        # Test individual comparisons - these should work semantically, not lexicographically
        assert FailureSeverity.INFO < FailureSeverity.WARNING, (
            "INFO should be less than WARNING semantically"
        )
        assert FailureSeverity.WARNING < FailureSeverity.CRITICAL, (
            "WARNING should be less than CRITICAL semantically"
        )
        assert FailureSeverity.INFO < FailureSeverity.CRITICAL, (
            "INFO should be less than CRITICAL semantically"
        )

        # Test that the string values can be in any order - the semantic ordering should still work
        # Even though "critical" < "info" < "warning" lexicographically
        assert FailureSeverity.CRITICAL > FailureSeverity.INFO, (
            "CRITICAL should be greater than INFO semantically"
        )
        assert FailureSeverity.CRITICAL > FailureSeverity.WARNING, (
            "CRITICAL should be greater than WARNING semantically"
        )
        assert FailureSeverity.WARNING > FailureSeverity.INFO, (
            "WARNING should be greater than INFO semantically"
        )

    @pytest.mark.unit
    def test_get_max_severity_failure_invalid_severity_skipped(self, caplog):
        """Test that expectations with invalid severity are skipped."""
        import logging

        # Create valid configurations first, then mock returning an invalid severity to
        # work around ValueError that is raised when attempting to set an invalid
        # severity in the constructor
        config1 = ExpectationConfiguration(
            type="expect_column_values_to_not_be_null",
            kwargs={"column": "test_column"},
            severity="critical",  # Start with valid severity
        )
        config2 = ExpectationConfiguration(
            type="expect_column_values_to_be_between",
            kwargs={
                "column": "test_column",
                "min_value": 0,
                "max_value": 100,
            },
            severity="warning",
        )

        # Mock the get method to return invalid severity for testing
        original_get = config1.get

        def mock_get_invalid(key, default=None):
            if key == "severity":
                return "invalid_severity"
            return original_get(key, default)

        config1.get = mock_get_invalid

        evr1 = ExpectationValidationResult(success=False, expectation_config=config1, result={})
        evr2 = ExpectationValidationResult(success=False, expectation_config=config2, result={})

        result = ExpectationSuiteValidationResult(
            suite_name="test_suite",
            success=False,
            results=[evr1, evr2],
        )

        # Capture log messages BEFORE calling the method
        caplog.set_level(
            logging.ERROR, logger="great_expectations.core.expectation_validation_result"
        )

        # Now call the method that should generate the log
        assert result.get_max_severity_failure() == FailureSeverity.WARNING

        # Verify that an error was logged about invalid severity
        assert any(
            "Invalid severity value 'invalid_severity'" in record.message
            for record in caplog.records
        )
        assert any(
            "expect_column_values_to_not_be_null" in record.message for record in caplog.records
        )

    @pytest.mark.unit
    def test_get_max_severity_failure_all_invalid_severities(self):
        """Test that None is returned when all failures have invalid severity."""

        # Create valid configurations first, then mock returning an invalid severity to
        # work around ValueError that is raised when attempting to set an invalid
        # severity in the constructor
        config1 = ExpectationConfiguration(
            type="expect_column_values_to_not_be_null",
            kwargs={"column": "test_column"},
            severity="critical",
        )
        config2 = ExpectationConfiguration(
            type="expect_column_values_to_be_between",
            kwargs={
                "column": "test_column",
                "min_value": 0,
                "max_value": 100,
            },
            severity="warning",
        )

        evr1 = ExpectationValidationResult(success=False, expectation_config=config1, result={})
        evr2 = ExpectationValidationResult(success=False, expectation_config=config2, result={})

        result = ExpectationSuiteValidationResult(
            suite_name="test_suite",
            success=False,
            results=[evr1, evr2],
        )

        # Mock the get method to return invalid severity for testing
        original_get1 = config1.get

        def mock_get_invalid1(key, default=None):
            if key == "severity":
                return "invalid_severity_1"
            return original_get1(key, default)

        config1.get = mock_get_invalid1

        original_get2 = config2.get

        def mock_get_invalid2(key, default=None):
            if key == "severity":
                return "invalid_severity_2"
            return original_get2(key, default)

        config2.get = mock_get_invalid2

        # Test that the method returns None when all severities are invalid
        assert result.get_max_severity_failure() is None


def _dict_config(config: dict[str, Any]) -> ExpectationConfiguration:
    """A plain dict where a configuration is expected, as a result built from serialized data
    can carry: `ExpectationValidationResult` stores `expectation_config` as given."""
    return cast("ExpectationConfiguration", config)


@pytest.mark.unit
def test_results_with_an_unloadable_expectation_config_are_not_equal_to_a_loadable_one():
    """A dict config that cannot be loaded as an ExpectationConfiguration is not equivalent to
    one that can, in either operand order. Comparing them must not read `NotImplemented` as a
    truth value (which made them equal through Python 3.13), and a result whose own config is a
    dict must not raise because a dict has no `isEquivalentTo`."""
    loadable = ExpectationValidationResult(
        success=True,
        expectation_config=ExpectationConfiguration(
            type="expect_column_to_exist", kwargs={"column": "a"}
        ),
    )
    unloadable = ExpectationValidationResult(
        success=True,
        expectation_config=_dict_config(
            {
                "expectation_type": "expect_column_values_to_be_unique",
                "kwargs": {"column": "b"},
                "meta": {},
            }
        ),
    )

    assert (loadable == unloadable) is False
    assert loadable != unloadable
    assert (unloadable == loadable) is False
    assert unloadable != loadable


@pytest.mark.unit
def test_a_result_with_a_config_is_not_equal_to_one_without() -> None:
    """Through Python 3.13 the configured side's `isEquivalentTo(None)` answered `NotImplemented`,
    which is truthy, so `configured == unconfigured` held in that direction only."""
    configured = ExpectationValidationResult(
        success=True,
        expectation_config=ExpectationConfiguration(
            type="expect_column_to_exist", kwargs={"column": "a"}
        ),
    )
    unconfigured = ExpectationValidationResult(success=True, expectation_config=None)

    assert (configured == unconfigured) is False
    assert (unconfigured == configured) is False
    assert configured != unconfigured
    assert unconfigured != configured


@pytest.mark.unit
@pytest.mark.parametrize(
    ("other_column", "expected_equal"),
    [pytest.param("b", True, id="same-dict"), pytest.param("c", False, id="different-dict")],
)
def test_results_whose_configs_are_both_dicts_compare_the_dicts(
    other_column: str, expected_equal: bool
) -> None:
    """Neither side has `isEquivalentTo`, so the dicts themselves decide."""

    def result(column: str) -> ExpectationValidationResult:
        return ExpectationValidationResult(
            success=True,
            expectation_config=_dict_config(
                {
                    "expectation_type": "expect_column_values_to_be_unique",
                    "kwargs": {"column": column},
                }
            ),
        )

    first, second = result("b"), result(other_column)

    assert (first == second) is expected_equal
    assert (first != second) is not expected_equal


@pytest.mark.unit
def test_a_dict_config_that_loads_is_equivalent_to_its_configuration_in_either_order() -> None:
    configured = ExpectationValidationResult(
        success=True,
        expectation_config=ExpectationConfiguration(
            type="expect_column_to_exist", kwargs={"column": "a"}
        ),
    )
    as_dict = ExpectationValidationResult(
        success=True,
        expectation_config=_dict_config(
            {"type": "expect_column_to_exist", "kwargs": {"column": "a"}}
        ),
    )

    assert configured == as_dict
    assert as_dict == configured
    assert not (configured != as_dict)
    assert not (as_dict != configured)


def _evr(
    expectation_id: str | None,
    success: bool | None,
    *,
    column: str = "shared_column",
    expectation_type: str = "expect_column_to_exist",
    kwargs: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
    expectation_config: Any = None,
) -> ExpectationValidationResult:
    """Build an individual result, deliberately carrying sensitive payloads that
    a comparison must never copy."""
    if expectation_config is None:
        expectation_config = ExpectationConfiguration(
            type=expectation_type,
            kwargs=kwargs if kwargs is not None else {"column": column},
            meta=meta if meta is not None else {},
            id=expectation_id,
        )
    return ExpectationValidationResult(
        success=success,
        expectation_config=expectation_config,
        result={
            "unexpected_count": 1,
            "unexpected_rows": [{"id": "do-not-copy-row"}],
        },
        exception_info={
            "raised_exception": True,
            "exception_traceback": "do-not-copy-traceback",
            "exception_message": "do-not-copy-message",
        },
    )


def _suite(
    results: list[ExpectationValidationResult],
) -> ExpectationSuiteValidationResult:
    return ExpectationSuiteValidationResult(
        success=all(result.success is True for result in results),
        results=results,
        suite_name="suite",
    )


class TestCompareSuiteValidationResults:
    @pytest.mark.unit
    def test_matches_by_id_across_reorder_and_reports_every_category(self) -> None:
        old_result = _suite(
            [
                _evr("a", True),
                _evr("b", False),
                _evr("c", True),
                _evr("d", False),
                _evr("e", True, column="column_e"),
                _evr("g", True),
                _evr("h", None),
                _evr("i", True, meta={"version": 1}),
            ]
        )
        # The new result is deliberately in a different order and mixes in
        # additions, removals, status flips, unknown statuses and a config edit.
        new_result = _suite(
            [
                _evr("i", True, meta={"version": 2}),
                _evr("h", True),
                _evr("f", True),
                _evr("e", False, column="column_e_renamed"),
                _evr("d", None),
                _evr("c", False),
                _evr("b", True),
                _evr("a", True),
            ]
        )

        comparison = compare_suite_validation_results(old_result, new_result)

        assert comparison.items == [
            ExpectationResultComparison(
                "a", ExpectationResultComparisonCategory.UNCHANGED, True, True
            ),
            ExpectationResultComparison(
                "b", ExpectationResultComparisonCategory.FAILURE_TO_SUCCESS, False, True
            ),
            ExpectationResultComparison(
                "c", ExpectationResultComparisonCategory.SUCCESS_TO_FAILURE, True, False
            ),
            ExpectationResultComparison(
                "d", ExpectationResultComparisonCategory.UNKNOWN, False, None
            ),
            ExpectationResultComparison(
                "e", ExpectationResultComparisonCategory.CONFIG_CHANGED, True, False
            ),
            ExpectationResultComparison(
                "f", ExpectationResultComparisonCategory.ONLY_IN_NEW, None, True
            ),
            ExpectationResultComparison(
                "g", ExpectationResultComparisonCategory.ONLY_IN_OLD, True, None
            ),
            ExpectationResultComparison(
                "h", ExpectationResultComparisonCategory.UNKNOWN, None, True
            ),
            ExpectationResultComparison(
                "i", ExpectationResultComparisonCategory.UNCHANGED, True, True
            ),
        ]

        grouped = comparison.by_category()
        assert {
            item.expectation_id
            for item in grouped[ExpectationResultComparisonCategory.SUCCESS_TO_FAILURE]
        } == {"c"}
        assert {
            item.expectation_id
            for item in grouped[ExpectationResultComparisonCategory.FAILURE_TO_SUCCESS]
        } == {"b"}
        assert {
            item.expectation_id
            for item in grouped[ExpectationResultComparisonCategory.CONFIG_CHANGED]
        } == {"e"}
        assert {
            item.expectation_id for item in grouped[ExpectationResultComparisonCategory.UNKNOWN]
        } == {"d", "h"}
        assert {
            item.expectation_id for item in grouped[ExpectationResultComparisonCategory.ONLY_IN_NEW]
        } == {"f"}
        assert {
            item.expectation_id for item in grouped[ExpectationResultComparisonCategory.ONLY_IN_OLD]
        } == {"g"}
        assert {
            item.expectation_id for item in grouped[ExpectationResultComparisonCategory.UNCHANGED]
        } == {"a", "i"}

    @pytest.mark.unit
    def test_items_are_sorted_by_id_independent_of_input_order(self) -> None:
        old_ids = ["z", "a", "m", "b"]
        new_ids = ["m", "b", "z", "a"]  # same IDs, different positions

        comparison = compare_suite_validation_results(
            _suite([_evr(expectation_id, True) for expectation_id in old_ids]),
            _suite([_evr(expectation_id, True) for expectation_id in new_ids]),
        )

        assert [item.expectation_id for item in comparison.items] == ["a", "b", "m", "z"]
        assert all(
            item.category == ExpectationResultComparisonCategory.UNCHANGED
            for item in comparison.items
        )

    @pytest.mark.unit
    def test_output_carries_only_identifier_category_and_status(self) -> None:
        old_result = _suite([_evr("a", True), _evr("b", False)])
        new_result = _suite([_evr("a", False), _evr("b", False)])

        comparison = compare_suite_validation_results(old_result, new_result)

        assert [field.name for field in fields(ExpectationResultComparison)] == [
            "expectation_id",
            "category",
            "old_success",
            "new_success",
        ]
        rendered = repr(comparison)
        assert "do-not-copy" not in rendered
        assert "unexpected_rows" not in rendered

    @pytest.mark.unit
    def test_config_change_takes_precedence_over_status_transition(self) -> None:
        # A status flip must be called a config change, not a data regression,
        # when the success-determining configuration differs.
        old_result = _suite(
            [
                _evr("regressed-looking", True, column="before"),
                _evr("unchanged-looking", True, column="before"),
                _evr("unknown-looking", None, column="before"),
            ]
        )
        new_result = _suite(
            [
                _evr("regressed-looking", False, column="after"),
                _evr("unchanged-looking", True, column="after"),
                _evr("unknown-looking", True, column="after"),
            ]
        )

        comparison = compare_suite_validation_results(old_result, new_result)

        assert comparison.items == [
            ExpectationResultComparison(
                "regressed-looking",
                ExpectationResultComparisonCategory.CONFIG_CHANGED,
                True,
                False,
            ),
            ExpectationResultComparison(
                "unchanged-looking",
                ExpectationResultComparisonCategory.CONFIG_CHANGED,
                True,
                True,
            ),
            ExpectationResultComparison(
                "unknown-looking",
                ExpectationResultComparisonCategory.CONFIG_CHANGED,
                None,
                True,
            ),
        ]

    @pytest.mark.unit
    def test_success_level_equivalence_ignores_meta_and_runtime_kwargs(self) -> None:
        # Meta-only and result_format-only differences do not decide success, so
        # they must not be reported as configuration changes.
        old_result = _suite(
            [
                _evr("meta", True, meta={"version": 1}),
                _evr(
                    "runtime",
                    True,
                    kwargs={"column": "shared_column", "result_format": "BASIC"},
                ),
            ]
        )
        new_result = _suite(
            [
                _evr("meta", True, meta={"version": 2, "notes": "changed"}),
                _evr(
                    "runtime",
                    True,
                    kwargs={"column": "shared_column", "result_format": "COMPLETE"},
                ),
            ]
        )

        comparison = compare_suite_validation_results(old_result, new_result)

        assert [item.category for item in comparison.items] == [
            ExpectationResultComparisonCategory.UNCHANGED,
            ExpectationResultComparisonCategory.UNCHANGED,
        ]

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("old_success", "new_success"),
        [
            pytest.param(None, True, id="old-unknown"),
            pytest.param(False, None, id="new-unknown"),
            pytest.param(None, None, id="both-unknown"),
        ],
    )
    def test_unknown_when_either_success_is_none(
        self, old_success: bool | None, new_success: bool | None
    ) -> None:
        comparison = compare_suite_validation_results(
            _suite([_evr("a", old_success)]),
            _suite([_evr("a", new_success)]),
        )

        assert comparison.items == [
            ExpectationResultComparison(
                "a",
                ExpectationResultComparisonCategory.UNKNOWN,
                old_success,
                new_success,
            )
        ]

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "missing_config",
        [
            pytest.param(None, id="no-expectation-config"),
            pytest.param(
                ExpectationConfiguration(
                    type="expect_column_to_exist", kwargs={"column": "x"}, id=None
                ),
                id="none-id",
            ),
            pytest.param(
                ExpectationConfiguration(
                    type="expect_column_to_exist", kwargs={"column": "x"}, id=""
                ),
                id="empty-id",
            ),
        ],
    )
    def test_rejects_results_without_a_non_null_id(self, missing_config: Any) -> None:
        # The unidentifiable result is sandwiched between keyed ones so its index
        # is reported rather than guessed by position.
        old_result = _suite([_evr("a", True), _evr(None, True, expectation_config=missing_config)])
        new_result = _suite([_evr("a", True)])

        with pytest.raises(ExpectationSuiteValidationResultComparisonError) as exc_info:
            compare_suite_validation_results(old_result, new_result)

        message = str(exc_info.value)
        assert "old" in message
        assert "indices [1]" in message
        assert "never by list position" in message

    @pytest.mark.unit
    def test_rejects_an_unreadable_expectation_config(self) -> None:
        old_result = _suite(
            [_evr("a", True, expectation_config=cast("ExpectationConfiguration", object()))]
        )
        new_result = _suite([_evr("a", True)])

        with pytest.raises(ExpectationSuiteValidationResultComparisonError) as exc_info:
            compare_suite_validation_results(old_result, new_result)

        assert "expected an ExpectationConfiguration or dict" in str(exc_info.value)

    @pytest.mark.unit
    def test_rejects_duplicate_ids_and_names_side_id_and_indices(self) -> None:
        old_result = _suite([_evr("dup", True), _evr("other", True), _evr("dup", False)])
        new_result = _suite([_evr("dup", True)])

        with pytest.raises(ExpectationSuiteValidationResultComparisonError) as exc_info:
            compare_suite_validation_results(old_result, new_result)

        message = str(exc_info.value)
        assert "old" in message
        assert "'dup' at indices [0, 2]" in message

    @pytest.mark.unit
    def test_reports_problems_from_both_sides_together(self) -> None:
        old_result = _suite([_evr("dup", True), _evr("dup", False)])
        new_result = _suite([_evr("unique", True), _evr(None, True, expectation_config=None)])

        with pytest.raises(ExpectationSuiteValidationResultComparisonError) as exc_info:
            compare_suite_validation_results(old_result, new_result)

        message = str(exc_info.value)
        assert "old result contains duplicate expectation ID(s)" in message
        assert "new result has expectation result(s) without a non-null expectation ID" in message

    @pytest.mark.unit
    def test_does_not_modify_inputs(self) -> None:
        old_result = _suite([_evr("a", True), _evr("b", False)])
        new_result = _suite([_evr("a", False), _evr("b", False), _evr("c", True)])
        old_before = old_result.to_json_dict()
        new_before = new_result.to_json_dict()

        compare_suite_validation_results(old_result, new_result)

        assert old_result.to_json_dict() == old_before
        assert new_result.to_json_dict() == new_before

    @pytest.mark.unit
    def test_supports_plain_dict_configs_in_either_operand_order(self) -> None:
        # A schema-loaded config id must be a UUID, as it is in serialized results.
        mixed_id = "22222222-2222-2222-2222-222222222222"
        dict_config_old = _dict_config(
            {"type": "expect_column_to_exist", "kwargs": {"column": "d"}, "id": "dict-pair"}
        )
        dict_config_changed = _dict_config(
            {"type": "expect_column_to_exist", "kwargs": {"column": "e"}, "id": "dict-pair"}
        )

        old_result = _suite(
            [
                _evr("dict-pair", True, expectation_config=dict_config_old),
                _evr(
                    mixed_id,
                    True,
                    expectation_config=_dict_config(
                        {
                            "type": "expect_column_to_exist",
                            "kwargs": {"column": "m"},
                            "id": mixed_id,
                        }
                    ),
                ),
            ]
        )
        new_result = _suite(
            [
                _evr("dict-pair", False, expectation_config=dict_config_changed),
                _evr(mixed_id, True, column="m"),
            ]
        )

        comparison = compare_suite_validation_results(old_result, new_result)

        assert comparison.items == [
            ExpectationResultComparison(
                mixed_id,
                ExpectationResultComparisonCategory.UNCHANGED,
                True,
                True,
            ),
            ExpectationResultComparison(
                "dict-pair",
                ExpectationResultComparisonCategory.CONFIG_CHANGED,
                True,
                False,
            ),
        ]

    @pytest.mark.unit
    def test_empty_suites_compare_to_nothing(self) -> None:
        comparison = compare_suite_validation_results(_suite([]), _suite([]))

        assert isinstance(comparison, ExpectationSuiteValidationResultComparison)
        assert comparison.items == []
        assert comparison.by_category() == {
            category: [] for category in ExpectationResultComparisonCategory
        }
