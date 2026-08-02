from __future__ import annotations

import math

import pytest

from thesistester.assistant import (
    ASSISTANT_CONTRACT_SCHEMA_VERSION,
    AssistantContractError,
    AssistantRequest,
    Capability,
    CapabilityMode,
    ConfirmationLevel,
    FEATURE_PARITY_REGISTRY,
    ResourceEnvelope,
    UnknownCapabilityError,
    get_capability,
    validate_capability_request,
)


def test_feature_parity_registry_covers_every_product_area():
    sections = {
        capability.capability_id.split(".", maxsplit=1)[0] for capability in FEATURE_PARITY_REGISTRY
    }

    assert sections == {
        "HOME",
        "DATA",
        "SETUP",
        "LEVELS",
        "SIGNALS",
        "BACKTEST",
        "GRID",
        "TIME",
        "VALIDATION",
        "EXPORT",
        "BUNDLE",
        "PORTFOLIO",
        "PIPELINE",
    }
    assert len({capability.capability_id for capability in FEATURE_PARITY_REGISTRY}) == len(
        FEATURE_PARITY_REGISTRY
    )
    assert all(
        capability.to_dict()["schema_version"] == ASSISTANT_CONTRACT_SCHEMA_VERSION
        for capability in FEATURE_PARITY_REGISTRY
    )


def test_registry_declares_current_headless_pipeline_as_executable():
    capability = get_capability("PIPELINE.run_experiment")

    assert capability.mode is CapabilityMode.EXECUTABLE
    assert capability.confirmation is ConfirmationLevel.EXPLICIT_CONFIRMATION
    assert capability.public_symbol == "thesistester.api.run_experiment"
    assert capability.resource_envelope.max_walk_forward_folds == 100


def test_unsupported_capability_requires_a_documented_limitation():
    with pytest.raises(AssistantContractError, match="must document a limitation"):
        Capability(
            capability_id="DATA.unsupported_example",
            ui_location="Data",
            user_action="Do something unsupported",
            public_symbol=None,
            mode=CapabilityMode.UNSUPPORTED,
            confirmation=ConfirmationLevel.NONE,
        )


def test_resource_envelope_rejects_zero_or_boolean_limits():
    with pytest.raises(AssistantContractError, match="positive integer"):
        ResourceEnvelope(max_grid_cells=0)
    with pytest.raises(AssistantContractError, match="positive integer"):
        ResourceEnvelope(max_simulations=True)


def test_request_round_trip_is_json_safe_and_fail_closed():
    request = AssistantRequest.from_dict(
        {
            "schema_version": ASSISTANT_CONTRACT_SCHEMA_VERSION,
            "capability_id": "PIPELINE.validate_run_spec",
            "payload": {"run_spec": {"schema_version": 1, "runs": []}},
        }
    )

    assert request.to_dict() == {
        "schema_version": ASSISTANT_CONTRACT_SCHEMA_VERSION,
        "capability_id": "PIPELINE.validate_run_spec",
        "payload": {"run_spec": {"schema_version": 1, "runs": []}},
    }
    assert validate_capability_request(request).capability_id == "PIPELINE.validate_run_spec"

    with pytest.raises(AssistantContractError, match="Unknown assistant request keys"):
        AssistantRequest.from_dict(
            {
                "capability_id": "PIPELINE.validate_run_spec",
                "payload": {},
                "unapproved": True,
            }
        )
    with pytest.raises(AssistantContractError, match="non-finite"):
        AssistantRequest(capability_id="PIPELINE.validate_run_spec", payload={"value": math.nan})


@pytest.mark.parametrize("schema_version", [True, 1.0])
def test_request_rejects_non_integer_schema_version_equivalents(schema_version):
    with pytest.raises(
        AssistantContractError, match="Unsupported assistant request schema_version"
    ):
        AssistantRequest(
            capability_id="PIPELINE.validate_run_spec",
            payload={},
            schema_version=schema_version,
        )

    with pytest.raises(
        AssistantContractError, match="Unsupported assistant request schema_version"
    ):
        AssistantRequest.from_dict(
            {
                "schema_version": schema_version,
                "capability_id": "PIPELINE.validate_run_spec",
                "payload": {},
            }
        )


def test_unknown_or_unsupported_capability_fails_before_execution():
    with pytest.raises(UnknownCapabilityError, match="Unknown assistant capability"):
        validate_capability_request(AssistantRequest(capability_id="DATA.not_real", payload={}))

    with pytest.raises(AssistantContractError, match="unsupported"):
        validate_capability_request(
            AssistantRequest(capability_id="GRID.manage_execution_defaults", payload={})
        )
