from __future__ import annotations

import json
import logging
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List, Optional, Union

from marshmallow import Schema, fields, post_dump, post_load, pre_dump
from typing_extensions import TypedDict

import great_expectations.exceptions as gx_exceptions
from great_expectations._docs_decorators import public_api
from great_expectations.alias_types import JSONValues  # noqa: TC001 # FIXME CoP
from great_expectations.compatibility.typing_extensions import override
from great_expectations.core.batch import (  # noqa: TC001 # FIXME CoP
    BatchMarkers,
    LegacyBatchDefinition,
)
from great_expectations.core.id_dict import BatchSpec  # noqa: TC001 # FIXME CoP
from great_expectations.core.run_identifier import RunIdentifier  # noqa: TC001 # FIXME CoP
from great_expectations.data_context.util import instantiate_class_from_config
from great_expectations.exceptions import ClassInstantiationError
from great_expectations.render import (
    AtomicRendererType,
    RenderedAtomicContent,
    RenderedAtomicContentSchema,
)
from great_expectations.types import SerializableDictDot
from great_expectations.util import (
    convert_to_json_serializable,  # noqa: TID251 # FIXME CoP
    ensure_json_serializable,  # noqa: TID251 # FIXME CoP
)

if TYPE_CHECKING:
    from great_expectations.expectations.expectation import Expectation
    from great_expectations.expectations.expectation_configuration import (
        ExpectationConfiguration,
    )
    from great_expectations.expectations.metadata_types import FailureSeverity
    from great_expectations.render.renderer.inline_renderer import InlineRendererConfig

logger = logging.getLogger(__name__)


def get_metric_kwargs_id(metric_kwargs: dict) -> str | None:
    ###
    #
    # WARNING
    # WARNING
    # THIS IS A PLACEHOLDER UNTIL WE HAVE REFACTORED EXPECTATIONS TO HANDLE THIS LOGIC THEMSELVES
    # WE ARE NO WORSE OFF THAN THE PREVIOUS SYSTEM, BUT NOT FULLY CUSTOMIZABLE
    # WARNING
    # WARNING
    #
    ###
    if metric_kwargs is None:
        metric_kwargs = {}

    if "metric_kwargs_id" in metric_kwargs:
        return metric_kwargs["metric_kwargs_id"]

    if "column" in metric_kwargs:
        return f"column={metric_kwargs.get('column')}"

    return None


def _expectation_configs_are_equivalent(
    config: Optional[Union[dict, ExpectationConfiguration]],
    other_config: Optional[Union[dict, ExpectationConfiguration]],
    match_type: str = "success",
) -> bool:
    """Whether two results' expectation configs are equivalent, in either operand order.

    A result stores its `expectation_config` as given, so either side may be a plain dict rather
    than an ExpectationConfiguration. A dict has no `isEquivalentTo`, so the comparison is asked
    of whichever side is a configuration; `isEquivalentTo` loads a dict operand itself. Two
    dicts are compared directly.
    """
    from great_expectations.expectations.expectation_configuration import (
        ExpectationConfiguration,
    )

    if config is None or other_config is None:
        return config is other_config
    if isinstance(config, ExpectationConfiguration):
        return config.isEquivalentTo(other_config, match_type=match_type)
    if isinstance(other_config, ExpectationConfiguration):
        return other_config.isEquivalentTo(config, match_type=match_type)
    return config == other_config


@public_api
class ExpectationValidationResult(SerializableDictDot):
    """An Expectation validation result.

    Args:
        success: Whether the Expectation validation was successful.
        expectation_config: The configuration of the Expectation that was validated.
        result: The result details that can take one of many result formats.
        meta: Metadata associated with the validation result.
        exception_info: Any exception information that was raised during validation. Takes the form:
            raised_exception: boolean
            exception_traceback: Optional, str
            exception_message: Optional, str
        rendered_content: Inline content for rendering.

    Raises:
        InvalidCacheValueError: Raised if the result does not pass validation.
    """

    def __init__(  # noqa: PLR0913 # FIXME CoP
        self,
        success: Optional[bool] = None,
        expectation_config: Optional[ExpectationConfiguration] = None,
        result: Optional[dict] = None,
        meta: Optional[dict] = None,
        exception_info: Optional[dict] = None,
        rendered_content: Union[RenderedAtomicContent, List[RenderedAtomicContent], None] = None,
        **kwargs: dict,
    ) -> None:
        if result and not self.validate_result_dict(result):
            raise gx_exceptions.InvalidCacheValueError(result)
        self.success = success
        self.expectation_config = expectation_config
        # TODO: re-add
        # assert_json_serializable(result, "result")
        if result is None:
            result = {}
        self.result = result
        if meta is None:
            meta = {}
        # We require meta information to be serializable, but do not convert until necessary
        ensure_json_serializable(meta)
        self.meta = meta
        self.exception_info = exception_info or {
            "raised_exception": False,
            "exception_traceback": None,
            "exception_message": None,
        }
        self.rendered_content = rendered_content

    @property
    @public_api
    def expectation(self) -> Expectation:
        """The Expectation object that produced this result."""
        if self.expectation_config is None:
            raise TypeError("Cannot construct Expectation: expectation_config is None.")  # noqa: TRY003
        return self.expectation_config.to_domain_obj()

    @override
    def __eq__(self, other):
        """ExpectationValidationResult equality ignores instance identity, relying only on properties."""  # noqa: E501 # FIXME CoP
        # NOTE: JPC - 20200213 - need to spend some time thinking about whether we want to
        # consistently allow dict as a comparison alternative in situations like these...
        # if isinstance(other, dict):
        #     try:
        #         other = ExpectationValidationResult(**other)
        #     except ValueError:
        #         return NotImplemented
        if not isinstance(other, self.__class__):
            # Delegate comparison to the other instance's __eq__.
            return other == self
        try:
            if self.result and other.result:
                common_keys = set(self.result.keys()) & other.result.keys()
                result_dict = self.to_json_dict()["result"]
                other_result_dict = other.to_json_dict()["result"]
                contents_equal = all(result_dict[k] == other_result_dict[k] for k in common_keys)
            else:
                contents_equal = False

            return all(
                (
                    self.success == other.success,
                    _expectation_configs_are_equivalent(
                        self.expectation_config, other.expectation_config, match_type="success"
                    ),
                    # Result is a dictionary allowed to have nested dictionaries that are still of complex types (e.g.  # noqa: E501 # FIXME CoP
                    # numpy) consequently, series' comparison can persist. Wrapping in all() ensures comparison is  # noqa: E501 # FIXME CoP
                    # handled appropriately.
                    not (self.result or other.result) or contents_equal,
                    self.meta == other.meta,
                    self.exception_info == other.exception_info,
                )
            )
        except (ValueError, TypeError):
            # if invalid comparisons are attempted, the objects are not equal.
            return False

    @override
    def __hash__(self) -> int:
        """Overrides the default implementation"""
        # note that it is possible for two results to be equal but have different hashes
        # this is because during comparison we only compare common keys
        if self.result:
            result_hash = hash(tuple(sorted(self.result.items())))
        else:
            result_hash = hash(None)

        # Handle expectation_config hash
        if self.expectation_config:
            config_hash = hash(self.expectation_config)
        else:
            config_hash = hash(None)

        return hash(
            (
                self.success,
                config_hash,
                result_hash,
                tuple(sorted(self.meta.items())) if self.meta else (),
                tuple(sorted(self.exception_info.items())) if self.exception_info else (),
            )
        )

    def __ne__(self, other):  # type: ignore[explicit-override] # FIXME
        # Negated implementation of '__eq__'. TODO the method should be deleted when it will coincide with __eq__.  # noqa: E501 # FIXME CoP
        # return not self == other
        if not isinstance(other, self.__class__):
            # Delegate comparison to the other instance's __ne__.
            return NotImplemented
        try:
            return any(
                (
                    self.success != other.success,
                    not _expectation_configs_are_equivalent(
                        self.expectation_config, other.expectation_config
                    ),
                    # TODO should it be wrapped in all()/any()? Since it is the only difference to __eq__:  # noqa: E501 # FIXME CoP
                    (self.result is None and other.result is not None)
                    or (self.result != other.result),
                    self.meta != other.meta,
                    self.exception_info != other.exception_info,
                )
            )
        except (ValueError, TypeError):
            # if invalid comparisons are attempted, the objects are not equal.
            return True

    @override
    def __repr__(self) -> str:
        """
        # TODO: <Alex>5/9/2022</Alex>
        This implementation is non-ideal (it was agreed to employ it for development expediency).  A better approach
        would consist of "__str__()" calling "__repr__()", while all output options are handled through state variables.
        """  # noqa: E501 # FIXME CoP
        json_dict: dict = self.to_json_dict()
        return json.dumps(json_dict, indent=2)

    @override
    def __str__(self) -> str:
        """
        # TODO: <Alex>5/9/2022</Alex>
        This implementation is non-ideal (it was agreed to employ it for development expediency).  A better approach
        would consist of "__str__()" calling "__repr__()", while all output options are handled through state variables.
        """  # noqa: E501 # FIXME CoP
        return json.dumps(self.to_json_dict(), indent=2)

    def render(self) -> None:
        """Renders content using the:
        - atomic prescriptive renderer for the expectation configuration associated with this
          ExpectationValidationResult to self.expectation_config.rendered_content
        - atomic diagnostic renderer for the expectation configuration associated with this
          ExpectationValidationResult to self.rendered_content.
        """
        inline_renderer_config: InlineRendererConfig = {
            "class_name": "InlineRenderer",
            "render_object": self,
        }
        module_name = "great_expectations.render.renderer.inline_renderer"
        inline_renderer = instantiate_class_from_config(
            config=inline_renderer_config,
            runtime_environment={},
            config_defaults={"module_name": module_name},
        )
        if not inline_renderer:
            raise ClassInstantiationError(
                module_name=module_name,
                package_name=None,
                class_name=inline_renderer_config["class_name"],
            )

        rendered_content: List[RenderedAtomicContent] = inline_renderer.get_rendered_content()

        self.rendered_content = [
            content_block
            for content_block in rendered_content
            if content_block.name.startswith(AtomicRendererType.DIAGNOSTIC)
        ]

        if self.expectation_config:
            self.expectation_config.rendered_content = [
                content_block
                for content_block in rendered_content
                if content_block.name.startswith(AtomicRendererType.PRESCRIPTIVE)
            ]

    @staticmethod
    def validate_result_dict(result):
        if result.get("unexpected_count") and result["unexpected_count"] < 0:
            return False
        if result.get("unexpected_percent") and (
            result["unexpected_percent"] < 0 or result["unexpected_percent"] > 100  # noqa: PLR2004 # FIXME CoP
        ):
            return False
        if result.get("missing_percent") and (
            result["missing_percent"] < 0 or result["missing_percent"] > 100  # noqa: PLR2004 # FIXME CoP
        ):
            return False
        if result.get("unexpected_percent_nonmissing") and (
            result["unexpected_percent_nonmissing"] < 0
            or result["unexpected_percent_nonmissing"] > 100  # noqa: PLR2004 # FIXME CoP
        ):
            return False
        return not (result.get("missing_count") and result["missing_count"] < 0)

    @public_api
    @override
    def to_json_dict(self) -> dict[str, JSONValues]:
        """Returns a JSON-serializable dict representation of this ExpectationValidationResult.

        Returns:
            A JSON-serializable dict representation of this ExpectationValidationResult.
        """
        myself = expectationValidationResultSchema.dump(self)
        # NOTE - JPC - 20191031: migrate to expectation-specific schemas that subclass result with properly-typed  # noqa: E501 # FIXME CoP
        # schemas to get serialization all-the-way down via dump
        if "expectation_config" in myself:
            myself["expectation_config"] = convert_to_json_serializable(
                myself["expectation_config"]
            )
        if "result" in myself:
            myself["result"] = convert_to_json_serializable(myself["result"])
        if "meta" in myself:
            myself["meta"] = convert_to_json_serializable(myself["meta"])
        if "exception_info" in myself:
            myself["exception_info"] = convert_to_json_serializable(myself["exception_info"])
        if "rendered_content" in myself:
            myself["rendered_content"] = convert_to_json_serializable(myself["rendered_content"])
        return myself

    def get_metric(self, metric_name, **kwargs):  # noqa: C901 #  too complex
        if not self.expectation_config:
            raise gx_exceptions.UnavailableMetricError(  # noqa: TRY003 # FIXME CoP
                "No ExpectationConfig found in this ExpectationValidationResult. Unable to "
                "return a metric."
            )

        metric_name_parts = metric_name.split(".")
        metric_kwargs_id = get_metric_kwargs_id(metric_kwargs=kwargs)

        if metric_name_parts[0] == self.expectation_config.type:
            curr_metric_kwargs = get_metric_kwargs_id(metric_kwargs=self.expectation_config.kwargs)
            if metric_kwargs_id != curr_metric_kwargs:
                raise gx_exceptions.UnavailableMetricError(
                    "Requested metric_kwargs_id ({}) does not match the configuration of this "
                    "ExpectationValidationResult ({}).".format(
                        metric_kwargs_id or "None", curr_metric_kwargs or "None"
                    )
                )
            if len(metric_name_parts) < 2:  # noqa: PLR2004 # FIXME CoP
                raise gx_exceptions.UnavailableMetricError(  # noqa: TRY003 # FIXME CoP
                    "Expectation-defined metrics must include a requested metric."
                )
            elif len(metric_name_parts) == 2:  # noqa: PLR2004 # FIXME CoP
                if metric_name_parts[1] == "success":
                    return self.success
                else:
                    raise gx_exceptions.UnavailableMetricError(  # noqa: TRY003 # FIXME CoP
                        "Metric name must have more than two parts for keys other than success."
                    )
            elif metric_name_parts[1] == "result":
                try:
                    if len(metric_name_parts) == 3:  # noqa: PLR2004 # FIXME CoP
                        return self.result.get(metric_name_parts[2])
                    elif metric_name_parts[2] == "details":
                        return self.result["details"].get(metric_name_parts[3])
                except KeyError:
                    raise gx_exceptions.UnavailableMetricError(  # noqa: TRY003 # FIXME CoP
                        f"Unable to get metric {metric_name} -- KeyError in "
                        "ExpectationValidationResult."
                    )
        raise gx_exceptions.UnavailableMetricError(f"Unrecognized metric name {metric_name}")  # noqa: TRY003 # FIXME CoP

    def describe_dict(self) -> dict:
        if self.expectation_config:
            expectation_type = self.expectation_config.type
            kwargs = self.expectation_config.kwargs
        else:
            expectation_type = None
            kwargs = None
        describe_dict = {
            "expectation_type": expectation_type,
            "success": self.success,
            "kwargs": kwargs,
            "result": self.result,
        }
        if self.exception_info.get("raised_exception"):
            describe_dict["exception_info"] = self.exception_info
        return convert_to_json_serializable(describe_dict)

    @public_api
    def describe(self) -> str:
        """JSON string description of this ExpectationValidationResult"""
        return json.dumps(self.describe_dict(), indent=4)


class ExpectationValidationResultSchema(Schema):
    success = fields.Bool(required=False, allow_none=True)
    expectation_config = fields.Nested(
        # marshmallow 3 rejects a callable returning a schema name; marshmallow 4 types it
        # fine, so unused-ignore keeps --warn-unused-ignores quiet on the newer major.
        lambda: "ExpectationConfigurationSchema",  # type: ignore[arg-type,return-value,unused-ignore] # FIXME CoP
        required=False,
        allow_none=True,
    )
    result = fields.Dict(required=False, allow_none=True)
    meta = fields.Dict(required=False, allow_none=True)
    exception_info = fields.Dict(required=False, allow_none=True)
    rendered_content = fields.List(
        fields.Nested(lambda: RenderedAtomicContentSchema, required=False, allow_none=True)
    )

    # noinspection PyUnusedLocal
    @pre_dump
    def convert_result_to_serializable(self, data, **kwargs):
        data = deepcopy(data)
        if isinstance(data, ExpectationValidationResult):
            data.result = convert_to_json_serializable(data.result)
        elif isinstance(data, dict):
            data["result"] = convert_to_json_serializable(data.get("result"))
        return data

    REMOVE_KEYS_IF_NONE = ["rendered_content"]

    @post_dump
    def clean_null_attrs(self, data: dict, **kwargs: dict) -> dict:
        """Removes the attributes in ExpectationValidationResultSchema.REMOVE_KEYS_IF_NONE during serialization if
        their values are None."""  # noqa: E501 # FIXME CoP
        from great_expectations.expectations.expectation_configuration import (
            ExpectationConfigurationSchema,
        )

        data = deepcopy(data)
        for key in ExpectationConfigurationSchema.REMOVE_KEYS_IF_NONE:
            if key in data and data[key] is None:
                data.pop(key)
        return data

    # noinspection PyUnusedLocal
    @post_load
    def make_expectation_validation_result(self, data, **kwargs):
        return ExpectationValidationResult(**data)


class ExpectationSuiteValidationResultMeta(TypedDict):
    active_batch_definition: LegacyBatchDefinition
    batch_markers: BatchMarkers
    batch_parameters: dict | None
    batch_spec: BatchSpec
    checkpoint_id: Optional[str]
    checkpoint_name: str
    expectation_suite_name: str
    great_expectations_version: str
    run_id: RunIdentifier
    validation_id: Optional[str]
    validation_time: str


@public_api
class ExpectationSuiteValidationResult(SerializableDictDot):
    """The result of a batch of data validated against an Expectation Suite.

    When a Checkpoint is run, it produces an instance of this class. The primary property
    of this class is `results`, which contains the individual ExpectationValidationResult
    instances which were produced by the Checkpoint run.

    ExpectationSuiteValidationResult.success will be True if all Expectations passed, otherwise it will be False.

    ExpectationSuiteValidationResult.statistics contains information about the Checkpoint run.:

    ```python
    {
        "evaluated_expectations": 14,
        "success_percent": 71.42857142857143,
        "successful_expectations": 10,
        "unsuccessful_expectations": 4
    }
    ```

    The meta property is an instance of ExpectationSuiteValidationResultMeta, and
    contains information identifying the resources used during the Checkpoint run.:

    ```python
    {
        "active_batch_definition": {
          "batch_identifiers": {},
          "data_asset_name": "taxi_data_1.csv",
          "data_connector_name": "default_inferred_data_connector_name",
          "datasource_name": "pandas"
        },
        "batch_markers": {
          "ge_load_time": "20220727T154327.630107Z",
          "pandas_data_fingerprint": "c4f929e6d4fab001fedc9e075bf4b612"
        },
        "batch_spec": {
          "path": "/Users/username/work/gx_example_projects/great_expectations/../data/taxi_data_1.csv"
        },
        "checkpoint_name": "single_validation_checkpoint",
        "expectation_suite_name": "taxi_suite_1",
        "great_expectations_version": "0.15.15",
        "run_id": {
          "run_name": "20220727-114327-my-run-name-template",
          "run_time": "2022-07-27T11:43:27.625252+00:00"
        },
        "validation_time": "20220727T154327.701100Z"
    }
    ```

    Args:
        success: Boolean indicating the success or failure of this collection of results, or None.
        results: List of ExpectationValidationResults, or None.
        suite_parameters: Dict of Suite Parameters used to produce these results, or None.
        statistics: Dict of values describing the results.
        meta: Instance of ExpectationSuiteValidationResult, a Dict of meta values, or None.
        batch_id: A unique identifier for the batch of data that was validated.
        result_url: A URL where the results are stored.
    """  # noqa: E501 # FIXME CoP

    def __init__(  # noqa: PLR0913 # FIXME CoP
        self,
        success: bool,
        results: list[ExpectationValidationResult],
        suite_name: str,
        suite_parameters: Optional[dict] = None,
        statistics: Optional[dict] = None,
        meta: Optional[ExpectationSuiteValidationResultMeta | dict] = None,
        batch_id: Optional[str] = None,
        result_url: Optional[str] = None,
        id: Optional[str] = None,
    ) -> None:
        self.success = success
        self.results = results
        self.suite_name = suite_name
        self.suite_parameters = suite_parameters or {}
        self.statistics = statistics or {}
        meta = meta or {}
        ensure_json_serializable(meta)  # We require meta information to be serializable.
        self.meta = meta
        self.batch_id = batch_id
        self.result_url = result_url
        self.id = id
        self._metrics: dict = {}

    @property
    def asset_name(self) -> str | None:
        if "active_batch_definition" in self.meta:
            return self.meta["active_batch_definition"].get("data_asset_name")
        return None

    @property
    @public_api
    def batch_parameters(self) -> dict | None:
        """The batch parameters used for this validation run, if any."""
        return self.meta.get("batch_parameters")

    def __eq__(self, other):  # type: ignore[explicit-override] # FIXME
        """ExpectationSuiteValidationResult equality ignores instance identity, relying only on properties."""  # noqa: E501 # FIXME CoP
        if not isinstance(other, self.__class__):
            # Delegate comparison to the other instance's __eq__.
            return NotImplemented
        return all(
            (
                self.success == other.success,
                self.results == other.results,
                self.suite_parameters == other.suite_parameters,
                self.statistics == other.statistics,
                self.meta == other.meta,
            )
        )

    @override
    def __hash__(self) -> int:
        return hash(
            (
                self.success,
                tuple(sorted(hash(result) for result in self.results)),
                tuple(sorted(self.suite_parameters.items())) if self.suite_parameters else (),
                tuple(sorted(self.statistics.items())) if self.statistics else (),
                tuple(sorted(self.meta.items())) if self.meta else (),
            )
        )

    def __repr__(self):  # type: ignore[explicit-override] # FIXME
        return json.dumps(self.to_json_dict(), indent=2)

    @override
    def __str__(self):
        return json.dumps(self.to_json_dict(), indent=2)

    @public_api
    @override
    def to_json_dict(self):
        """Returns a JSON-serializable dict representation of this ExpectationSuiteValidationResult.

        Returns:
            A JSON-serializable dict representation of this ExpectationSuiteValidationResult.
        """
        myself = deepcopy(self)
        # NOTE - JPC - 20191031: migrate to expectation-specific schemas that subclass result with properly-typed  # noqa: E501 # FIXME CoP
        # schemas to get serialization all-the-way down via dump
        myself["suite_parameters"] = convert_to_json_serializable(myself["suite_parameters"])
        myself["statistics"] = convert_to_json_serializable(myself["statistics"])
        myself["meta"] = convert_to_json_serializable(myself["meta"])
        myself["results"] = [convert_to_json_serializable(result) for result in myself["results"]]
        myself = expectationSuiteValidationResultSchema.dump(myself)
        return myself

    def get_metric(self, metric_name, **kwargs):  # noqa: C901 #  too complex
        metric_name_parts = metric_name.split(".")
        metric_kwargs_id = get_metric_kwargs_id(metric_kwargs=kwargs)

        metric_value = None
        # Expose overall statistics
        if metric_name_parts[0] == "statistics":
            if len(metric_name_parts) == 2:  # noqa: PLR2004 # FIXME CoP
                return self.statistics.get(metric_name_parts[1])
            else:
                raise gx_exceptions.UnavailableMetricError(f"Unrecognized metric {metric_name}")  # noqa: TRY003 # FIXME CoP

        # Expose expectation-defined metrics
        elif metric_name_parts[0].lower().startswith("expect_"):
            # Check our cache first
            if (metric_name, metric_kwargs_id) in self._metrics:
                return self._metrics[(metric_name, metric_kwargs_id)]
            else:
                for result in self.results:
                    try:
                        if metric_name_parts[0] == result.expectation_config.type:
                            metric_value = result.get_metric(metric_name, **kwargs)
                            break
                    except gx_exceptions.UnavailableMetricError:
                        pass
                if metric_value is not None:
                    self._metrics[(metric_name, metric_kwargs_id)] = metric_value
                    return metric_value

        raise gx_exceptions.UnavailableMetricError(  # noqa: TRY003 # FIXME CoP
            f"Metric {metric_name} with metric_kwargs_id {metric_kwargs_id} is not available."
        )

    def get_failed_validation_results(
        self,
    ) -> ExpectationSuiteValidationResult:
        validation_results = [result for result in self.results if not result.success]

        successful_expectations = sum(exp.success or False for exp in validation_results)
        evaluated_expectations = len(validation_results)
        unsuccessful_expectations = evaluated_expectations - successful_expectations
        success = successful_expectations == evaluated_expectations
        try:
            success_percent = successful_expectations / evaluated_expectations * 100
        except ZeroDivisionError:
            success_percent = None
        statistics = {
            "successful_expectations": successful_expectations,
            "evaluated_expectations": evaluated_expectations,
            "unsuccessful_expectations": unsuccessful_expectations,
            "success_percent": success_percent,
            "success": success,
        }

        return ExpectationSuiteValidationResult(
            success=success,
            results=validation_results,
            suite_name=self.suite_name,
            suite_parameters=self.suite_parameters,
            statistics=statistics,
            meta=self.meta,
        )

    def describe_dict(self) -> dict:
        return convert_to_json_serializable(
            {
                "success": self.success,
                "statistics": self.statistics,
                "expectations": [expectation.describe_dict() for expectation in self.results],
                "result_url": self.result_url,
            }
        )

    @public_api
    def describe(self) -> str:
        """JSON string description of this ExpectationSuiteValidationResult"""
        return json.dumps(self.describe_dict(), indent=4)

    @public_api
    def get_max_severity_failure(self) -> FailureSeverity | None:
        """Get the maximum severity failure for Expectations in the validation result.

        Returns the maximum severity level among failed expectations. The severity levels
        are ordered as: CRITICAL > WARNING > INFO. If no failures exist, returns None.

        Returns:
            The maximum severity failure level, or None if no failures exist.
        """
        from great_expectations.expectations import metadata_types

        if not self.results:
            return None

        max_severity = None

        for result in self.results:
            # Only consider failed expectations
            if not result.success:
                if result.expectation_config is None:
                    logger.error(
                        f"Expectation configuration is None for failed expectation "
                        f"(Validation Result ID: {self.id}). "
                        f"Skipping this result."
                    )
                    continue

                severity_str = result.expectation_config.get("severity")
                try:
                    severity = metadata_types.FailureSeverity(severity_str)

                    # Short-circuit: highest possible severity level found
                    if severity == metadata_types.FailureSeverity.CRITICAL:
                        return severity

                    if max_severity is None or severity > max_severity:
                        max_severity = severity

                except ValueError:
                    logger.exception(
                        f"Invalid severity value '{severity_str}' found in expectation "
                        f"'{result.expectation_config.type}' "
                        f"(Validation Result ID: {self.id}). "
                        f"Skipping this result."
                    )

        return max_severity


@public_api
class ExpectationResultComparisonCategory(str, Enum):
    """How a single expectation's outcome differs between two validation results.

    Members:
        ONLY_IN_OLD: The expectation ID appears only in the older result.
        ONLY_IN_NEW: The expectation ID appears only in the newer result.
        SUCCESS_TO_FAILURE: The expectation succeeded in the old result and
            fails in the new one (a new failure).
        FAILURE_TO_SUCCESS: The expectation failed in the old result and
            succeeds in the new one (a recovery).
        UNCHANGED: Both results report the same `success` value under
            success-equivalent configurations.
        UNKNOWN: At least one side does not report a `success` value (it is
            None), so no transition can be determined.
        CONFIG_CHANGED: The same ID carries configurations that are not
            success-equivalent; the condition deciding success changed, so the
            status difference must not be read as a data regression.
    """

    ONLY_IN_OLD = "only_in_old"
    ONLY_IN_NEW = "only_in_new"
    SUCCESS_TO_FAILURE = "success_to_failure"
    FAILURE_TO_SUCCESS = "failure_to_success"
    UNCHANGED = "unchanged"
    UNKNOWN = "unknown"
    CONFIG_CHANGED = "config_changed"


@public_api
@dataclass(frozen=True)
class ExpectationResultComparison:
    """One expectation's status difference between two validation results.

    Only identifying and status information is carried: result payloads,
    `unexpected_rows`, exception tracebacks, and other validation data are not
    copied from either input.

    Args:
        expectation_id: The non-null expectation ID used as the match key.
        category: The kind of difference observed.
        old_success: `success` in the older result, or None if the ID is absent
            there.
        new_success: `success` in the newer result, or None if the ID is absent
            there.
    """

    expectation_id: str
    category: ExpectationResultComparisonCategory
    old_success: Optional[bool]
    new_success: Optional[bool]


@public_api
@dataclass(frozen=True)
class ExpectationSuiteValidationResultComparison:
    """Item-by-item comparison of two ExpectationSuiteValidationResults.

    Args:
        items: One ExpectationResultComparison per expectation ID, sorted
            stably by expectation ID.
    """

    items: List[ExpectationResultComparison]

    def by_category(
        self,
    ) -> dict[ExpectationResultComparisonCategory, List[ExpectationResultComparison]]:
        """Return the comparison items grouped by category, in ID-sorted order.

        Every category is present as a key, with an empty list when no item was
        classified into it.
        """
        grouped: dict[
            ExpectationResultComparisonCategory,
            list[ExpectationResultComparison],
        ] = {category: [] for category in ExpectationResultComparisonCategory}
        for item in self.items:
            grouped[item.category].append(item)
        return grouped


@public_api
def compare_suite_validation_results(
    old_result: ExpectationSuiteValidationResult,
    new_result: ExpectationSuiteValidationResult,
) -> ExpectationSuiteValidationResultComparison:
    """Compare two ExpectationSuiteValidationResults item by item.

    Individual expectation results are matched on the non-null `id` of their
    `expectation_config`, never by their position in the results list. Each ID
    is reported once, and the returned items are sorted stably by ID. Each item
    carries only the expectation ID, its category, and the two `success`
    values; result payloads, `unexpected_rows`, and exception information are
    not copied.

    Each pair matched by ID is classified as follows:

    - `SUCCESS_TO_FAILURE`: succeeded in the old result, failed in the new one.
    - `FAILURE_TO_SUCCESS`: failed in the old result, succeeded in the new one.
    - `UNCHANGED`: both sides report the same `success` value.
    - `UNKNOWN`: either side's `success` is None, so no transition is known.
    - `CONFIG_CHANGED`: the two configurations are not equivalent at the
      `success` match level. The pair is reported as a configuration change
      rather than a data regression or recovery, because the condition that
      decides success is not the same. Equivalence follows
      `ExpectationConfiguration.isEquivalentTo` with `match_type="success"`,
      the same rule used when comparing ExpectationValidationResults; changes
      that do not affect the success condition (e.g. meta-only edits) are not
      treated as configuration changes.

    IDs found on only one side are classified `ONLY_IN_OLD` or `ONLY_IN_NEW`.

    Note:
        This comparison only describes the two existing result sets. The
        results may have been produced against different batches or with
        different suite configurations, so a status difference by itself cannot
        prove a data root cause. No validation is run, and neither input is
        modified.

    Args:
        old_result: The earlier ExpectationSuiteValidationResult.
        new_result: The later ExpectationSuiteValidationResult.

    Returns:
        The per-ID comparison, sorted by expectation ID.

    Raises:
        ExpectationSuiteValidationResultComparisonError: If either result
            contains an expectation result without a non-null expectation ID,
            or contains the same expectation ID more than once.
    """
    old_by_id, old_problems = _index_results_by_expectation_id(old_result, "old")
    new_by_id, new_problems = _index_results_by_expectation_id(new_result, "new")
    problems = old_problems + new_problems
    if problems:
        raise gx_exceptions.ExpectationSuiteValidationResultComparisonError(
            "Cannot compare ExpectationSuiteValidationResults by expectation ID: "
            + "; ".join(problems)
            + ". Results are matched only by non-null expectation ID, never by "
            "list position."
        )

    items: list[ExpectationResultComparison] = []
    for expectation_id in sorted(set(old_by_id) | set(new_by_id)):
        old_item = old_by_id.get(expectation_id)
        new_item = new_by_id.get(expectation_id)
        if old_item is not None and new_item is not None:
            category = _classify_matched_pair(old_item, new_item)
            old_success = old_item.success
            new_success = new_item.success
        elif new_item is not None:
            category = ExpectationResultComparisonCategory.ONLY_IN_NEW
            old_success = None
            new_success = new_item.success
        else:
            category = ExpectationResultComparisonCategory.ONLY_IN_OLD
            old_success = old_item.success if old_item is not None else None
            new_success = None

        items.append(
            ExpectationResultComparison(
                expectation_id=expectation_id,
                category=category,
                old_success=old_success,
                new_success=new_success,
            )
        )

    return ExpectationSuiteValidationResultComparison(items=items)


def _classify_matched_pair(
    old_item: ExpectationValidationResult,
    new_item: ExpectationValidationResult,
) -> ExpectationResultComparisonCategory:
    """Classify two results sharing an expectation ID."""
    old_success = old_item.success
    new_success = new_item.success
    if not _expectation_configs_are_equivalent(
        old_item.expectation_config,
        new_item.expectation_config,
        match_type="success",
    ):
        return ExpectationResultComparisonCategory.CONFIG_CHANGED
    if old_success is None or new_success is None:
        return ExpectationResultComparisonCategory.UNKNOWN
    if old_success == new_success:
        return ExpectationResultComparisonCategory.UNCHANGED
    if old_success is True and new_success is False:
        return ExpectationResultComparisonCategory.SUCCESS_TO_FAILURE
    return ExpectationResultComparisonCategory.FAILURE_TO_SUCCESS


def _index_results_by_expectation_id(
    suite_result: ExpectationSuiteValidationResult, side: str
) -> tuple[dict[str, ExpectationValidationResult], list[str]]:
    """Index one suite result's individual results by non-null expectation ID.

    Returns the ID-to-result mapping alongside human-readable descriptions of
    any missing or duplicate IDs that make the side ambiguous to match.
    """
    by_id: dict[str, ExpectationValidationResult] = {}
    first_index_by_id: dict[str, int] = {}
    duplicate_indices: dict[str, list[int]] = {}
    missing_indices: list[int] = []

    for index, result in enumerate(suite_result.results):
        expectation_id = _get_expectation_id(result.expectation_config)
        if expectation_id is None:
            missing_indices.append(index)
        elif expectation_id in by_id:
            if expectation_id not in duplicate_indices:
                duplicate_indices[expectation_id] = [first_index_by_id[expectation_id]]
            duplicate_indices[expectation_id].append(index)
        else:
            by_id[expectation_id] = result
            first_index_by_id[expectation_id] = index

    problems: list[str] = []
    if missing_indices:
        problems.append(
            f"the {side} result has expectation result(s) without a non-null "
            f"expectation ID at indices {missing_indices}"
        )
    if duplicate_indices:
        details = ", ".join(
            f"{expectation_id!r} at indices {indices}"
            for expectation_id, indices in sorted(duplicate_indices.items())
        )
        problems.append(f"the {side} result contains duplicate expectation ID(s): {details}")
    return by_id, problems


def _get_expectation_id(
    expectation_config: Union[ExpectationConfiguration, dict, None],
) -> Optional[str]:
    """Return the non-empty expectation ID of a result's config in either form.

    A result stores `expectation_config` as given, so it can be an
    ExpectationConfiguration or a plain dict (or None). None and empty strings
    do not provide a usable match key.
    """
    from great_expectations.expectations.expectation_configuration import (
        ExpectationConfiguration,
    )

    if expectation_config is None:
        return None
    if isinstance(expectation_config, ExpectationConfiguration):
        expectation_id = expectation_config.id
    elif isinstance(expectation_config, dict):
        expectation_id = expectation_config.get("id")
    else:
        raise gx_exceptions.ExpectationSuiteValidationResultComparisonError(  # noqa: TRY003 # FIXME CoP
            "Cannot read expectation ID from expectation_config of type "
            f"{type(expectation_config).__name__}; expected an "
            "ExpectationConfiguration or dict."
        )
    if expectation_id is None:
        return None
    expectation_id = str(expectation_id)
    return expectation_id if expectation_id.strip() else None


class ExpectationSuiteValidationResultSchema(Schema):
    success = fields.Bool()
    results = fields.List(fields.Nested(ExpectationValidationResultSchema))
    suite_name = fields.String(required=True, allow_none=False)
    suite_parameters = fields.Dict()
    statistics = fields.Dict()
    meta = fields.Dict(allow_none=True)
    id = fields.UUID(required=False, allow_none=True)

    # noinspection PyUnusedLocal
    @pre_dump
    def prepare_dump(self, data, **kwargs):
        data = deepcopy(data)
        if isinstance(data, ExpectationSuiteValidationResult):
            data.meta = convert_to_json_serializable(data=data.meta)
            data.statistics = convert_to_json_serializable(data=data.statistics)
        elif isinstance(data, dict):
            data["meta"] = convert_to_json_serializable(data=data.get("meta"))
            data["statistics"] = convert_to_json_serializable(data=data.get("statistics"))
        return data

    def _convert_uuids_to_str(self, data):
        """
        Utilize UUID for data validation but convert to string before usage in business logic
        """
        attr = "id"
        uuid_val = data.get(attr)
        if uuid_val:
            data[attr] = str(uuid_val)
        return data

    # noinspection PyUnusedLocal
    @post_load
    def make_expectation_suite_validation_result(self, data, **kwargs):
        data = self._convert_uuids_to_str(data=data)
        return ExpectationSuiteValidationResult(**data)


expectationSuiteValidationResultSchema = ExpectationSuiteValidationResultSchema()
expectationValidationResultSchema = ExpectationValidationResultSchema()
