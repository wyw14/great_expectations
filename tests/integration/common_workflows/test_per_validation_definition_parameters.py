"""End-to-end coverage for per-Validation Definition parameter overrides on
``Checkpoint.run()``.

One checkpoint run validates two Validation Definitions that share a monthly batch
definition and an expectation suite:

* the global ``batch_parameters`` select January 2018; the February definition
  overrides the ``month`` key and inherits ``year``;
* the global ``expectation_parameters`` permit ``passenger_count`` up to 10; the
  February definition replaces that one key with 0 (which the taxi data cannot
  satisfy) while inheriting every other key.

The tests prove the two validations select different batches, resolve different
expectation parameters, share one run, and leave the caller's inputs untouched.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from unittest import mock

import pytest

import great_expectations as gx
import great_expectations.expectations as gxe
from great_expectations.checkpoint.checkpoint import Checkpoint
from great_expectations.core.expectation_suite import ExpectationSuite
from great_expectations.core.validation_definition import ValidationDefinition
from great_expectations.exceptions import (
    CheckpointRunValidationDefinitionParameterOverrideError,
)

if TYPE_CHECKING:
    from great_expectations.data_context.data_context.abstract_data_context import (
        AbstractDataContext,
    )

DATASOURCE_NAME = "per-vd taxi files"
ASSET_NAME = "taxi csv"
BATCH_DEFINITION_NAME = "monthly taxi"
SUITE_NAME = "passenger suite"
JANUARY_VALIDATION_NAME = "january validation"
FEBRUARY_VALIDATION_NAME = "february validation"
CHECKPOINT_NAME = "per-vd checkpoint"
BATCHING_REGEX = r"yellow_tripdata_sample_(?P<year>\d{4})-(?P<month>\d{2})\.csv"
TAXI_DATA_DIR = "tests/test_sets/taxi_yellow_tripdata_samples"

GLOBAL_BATCH_PARAMETERS = {"year": 2018, "month": 1}
GLOBAL_EXPECTATION_PARAMETERS = {"max_passengers": 10}


@pytest.fixture
def context() -> AbstractDataContext:
    return gx.get_context(mode="ephemeral")


@pytest.fixture
def checkpoint(context: AbstractDataContext) -> Checkpoint:
    asset = context.data_sources.add_pandas_filesystem(
        DATASOURCE_NAME,
        base_directory=TAXI_DATA_DIR,  # type: ignore [arg-type]
    ).add_csv_asset(name=ASSET_NAME)
    batch_definition = asset.add_batch_definition_monthly(
        BATCH_DEFINITION_NAME, re.compile(BATCHING_REGEX)
    )

    suite = context.suites.add(
        ExpectationSuite(
            SUITE_NAME,
            expectations=[
                gxe.ExpectColumnValuesToBeBetween(
                    column="passenger_count",
                    min_value=0,
                    max_value={"$PARAMETER": "max_passengers"},
                )
            ],
        )
    )
    january_validation = context.validation_definitions.add(
        ValidationDefinition(name=JANUARY_VALIDATION_NAME, data=batch_definition, suite=suite)
    )
    february_validation = context.validation_definitions.add(
        ValidationDefinition(name=FEBRUARY_VALIDATION_NAME, data=batch_definition, suite=suite)
    )
    return context.checkpoints.add(
        Checkpoint(
            name=CHECKPOINT_NAME,
            validation_definitions=[january_validation, february_validation],
        )
    )


@pytest.mark.filesystem
def test_single_run_applies_per_validation_definition_parameters(
    checkpoint: Checkpoint,
) -> None:
    batch_parameters_by_validation_definition = {
        # "year" is inherited from the global mapping; only "month" is replaced.
        FEBRUARY_VALIDATION_NAME: {"month": 2},
    }
    expectation_parameters_by_validation_definition = {
        # Replacing this one key makes the February validation impossible to satisfy.
        FEBRUARY_VALIDATION_NAME: {"max_passengers": 0},
    }

    result = checkpoint.run(
        batch_parameters=dict(GLOBAL_BATCH_PARAMETERS),
        expectation_parameters=dict(GLOBAL_EXPECTATION_PARAMETERS),
        batch_parameters_by_validation_definition=batch_parameters_by_validation_definition,
        expectation_parameters_by_validation_definition=(
            expectation_parameters_by_validation_definition
        ),
    )

    validation_results = tuple(result.run_results.values())
    assert len(validation_results) == 2
    january_result, february_result = validation_results

    # Both results belong to the same run.
    assert january_result.meta["run_id"] is february_result.meta["run_id"] is result.run_id

    # Each validation actually selected its own batch using its own parameters.
    assert january_result.meta["batch_parameters"] == {"year": 2018, "month": 1}
    assert february_result.meta["batch_parameters"] == {"year": 2018, "month": 2}
    january_key, february_key = tuple(result.run_results.keys())
    assert january_key.batch_identifier != february_key.batch_identifier

    # Global expectation parameters hold for January; the overridden threshold fails February.
    assert january_result.success is True
    assert february_result.success is False


@pytest.mark.filesystem
def test_per_validation_definition_parameters_do_not_mutate_caller_input(
    checkpoint: Checkpoint,
) -> None:
    global_batch_parameters = dict(GLOBAL_BATCH_PARAMETERS)
    global_expectation_parameters = dict(GLOBAL_EXPECTATION_PARAMETERS)
    batch_overrides = {FEBRUARY_VALIDATION_NAME: {"month": 2}}
    expectation_overrides = {FEBRUARY_VALIDATION_NAME: {"max_passengers": 0}}

    checkpoint.run(
        batch_parameters=global_batch_parameters,
        expectation_parameters=global_expectation_parameters,
        batch_parameters_by_validation_definition=batch_overrides,
        expectation_parameters_by_validation_definition=expectation_overrides,
    )

    assert global_batch_parameters == GLOBAL_BATCH_PARAMETERS
    assert global_expectation_parameters == GLOBAL_EXPECTATION_PARAMETERS
    assert batch_overrides == {FEBRUARY_VALIDATION_NAME: {"month": 2}}
    assert expectation_overrides == {FEBRUARY_VALIDATION_NAME: {"max_passengers": 0}}


@pytest.mark.filesystem
def test_unknown_validation_definition_override_raises_before_any_validation(
    checkpoint: Checkpoint,
) -> None:
    with mock.patch.object(ValidationDefinition, "run") as mock_run:
        with pytest.raises(CheckpointRunValidationDefinitionParameterOverrideError) as e:
            checkpoint.run(
                batch_parameters=dict(GLOBAL_BATCH_PARAMETERS),
                batch_parameters_by_validation_definition={
                    "not a validation of this checkpoint": {"month": 3}
                },
            )

    assert "not a validation of this checkpoint" in str(e.value)
    assert JANUARY_VALIDATION_NAME in str(e.value)
    assert FEBRUARY_VALIDATION_NAME in str(e.value)
    mock_run.assert_not_called()
