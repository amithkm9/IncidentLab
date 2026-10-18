import json
from dataclasses import FrozenInstanceError, replace

import pytest

from incidentlab.contracts import CHECKOUT_CONTRACT, validate_checkout_response


@pytest.mark.parametrize(
    "sku,total,cents", [("notebook", 12, 1200), ("lamp", 45.0, 4500), ("mug", 8.5, 850)]
)
def test_contract_validates_expected_sku_and_exact_cents(sku, total, cents):
    check = validate_checkout_response(
        json.dumps({"sku": sku, "total": total, "request_id": "request-1"}), 200, sku
    )
    assert check["passed"]
    assert check["evaluated"]
    assert check["expected_total_cents"] == check["observed_total_cents"] == cents
    assert check["violations"] == []


@pytest.mark.parametrize(
    "body,violation",
    [
        ('{"sku":"notebook","total":true,"request_id":"r"}', "invalid_total_type"),
        ('{"sku":"notebook","total":"12.00","request_id":"r"}', "invalid_total_type"),
        ('{"sku":"notebook","total":null,"request_id":"r"}', "invalid_total_type"),
        ('{"sku":"notebook","total":NaN,"request_id":"r"}', "invalid_json"),
        ('{"sku":"notebook","total":Infinity,"request_id":"r"}', "invalid_json"),
        ('{"sku":"notebook","total":1e10000,"request_id":"r"}', "invalid_total_range"),
        ('{"sku":"notebook","total":1e99999999999999999999,"request_id":"r"}', "invalid_json"),
        ('{"sku":"notebook","total":1e-99999999999999999999,"request_id":"r"}', "invalid_json"),
        ('{"sku":"notebook","total":-12,"request_id":"r"}', "invalid_total_range"),
        ('{"sku":"notebook","total":12.001,"request_id":"r"}', "fractional_cent_total"),
        (
            '{"sku":"notebook","total":12.000000000000000000000000000001,"request_id":"r"}',
            "fractional_cent_total",
        ),
        ('{"sku":"notebook","total":13,"request_id":"r"}', "price_mismatch"),
        ('{"sku":"lamp","total":12,"request_id":"r"}', "sku_mismatch"),
        ('{"sku":false,"total":12,"request_id":"r"}', "invalid_sku"),
        ('{"sku":"notebook","total":12}', "missing_request_id"),
        ('{"sku":"notebook","total":12,"request_id":true}', "invalid_request_id"),
        ('{"sku":"notebook","request_id":"r"}', "missing_total"),
        ('{"sku":"notebook","total":12,"request_id":"r","discount":0}', "unexpected_fields"),
        ('{"sku":"notebook","total":13,"total":12,"request_id":"r"}', "invalid_json"),
        ("[]", "invalid_response_object"),
        ("null", "invalid_response_object"),
        ("", "invalid_json"),
        ('{"sku":', "invalid_json"),
        (b"\xff", "invalid_json"),
    ],
)
def test_http_200_alone_never_passes_invalid_contract(body, violation):
    check = validate_checkout_response(body, 200, "notebook")
    assert not check["passed"]
    assert check["evaluated"]
    assert violation in check["violations"]


def test_decimal_zero_padding_does_not_create_a_fractional_cent():
    body = '{"sku":"notebook","total":12.000000000000000000000000000000,"request_id":"r"}'
    assert validate_checkout_response(body, 200, "notebook")["passed"]


def test_non_200_response_is_not_claimed_as_semantically_evaluated():
    check = validate_checkout_response('{"error":"upstream_error"}', 502, "notebook")
    assert check["evaluated"] is False
    assert check["passed"] is False
    assert check["violations"] == ["http_status_not_ok"]


def test_unknown_requested_product_cannot_pass_a_matching_response():
    check = validate_checkout_response(
        '{"sku":"unknown","total":12,"request_id":"r"}', 200, "unknown"
    )
    assert not check["passed"]
    assert "unknown_requested_sku" in check["violations"]


def test_contract_is_immutable_and_its_provenance_tracks_definition_changes():
    definition = CHECKOUT_CONTRACT.metadata()
    assert len(definition["sha256"]) == 64
    assert definition["expected_totals_cents"] == {"notebook": 1200, "lamp": 4500, "mug": 850}
    definition["expected_totals_cents"]["notebook"] = 1
    assert CHECKOUT_CONTRACT.expected_totals_cents["notebook"] == 1200
    with pytest.raises(FrozenInstanceError):
        CHECKOUT_CONTRACT.version = "mutated"
    assert replace(CHECKOUT_CONTRACT, version="2.0.0").sha256 != CHECKOUT_CONTRACT.sha256
    assert (
        replace(CHECKOUT_CONTRACT, prices=(("notebook", 1300),)).sha256 != CHECKOUT_CONTRACT.sha256
    )
