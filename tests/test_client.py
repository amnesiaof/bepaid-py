"""Tests for the bepaid client using a mocked httpx transport."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from bepaid import AsyncBepaidClient, BepaidClient, BepaidError, models
from bepaid.client import (
    parse_checkout_webhook,
    parse_subscription_webhook,
    parse_webhook,
    verify_webhook_auth,
    verify_webhook_signature,
)
from bepaid.errors import ApiError
from bepaid.models import (
    AdditionalData,
    ApmConfirmRequest,
    ApmPaymentRequest,
    ApmPayoutRequest,
    ApmRefundRequest,
    AuthorizationRequest,
    BalanceRequest,
    CancelSubscriptionRequest,
    CaptureRequest,
    ChargeCreditCard,
    ChargeRequest,
    CheckoutOrder,
    CheckoutOrderAdditionalData,
    CheckoutRequest,
    CheckupRequest,
    CreateTokenRequest,
    CreditCardRaw,
    CurrencyQueryRequest,
    CustomerRecord,
    CustomField,
    CustomFields,
    EripDevice,
    Fiscalization,
    FiscalizationPosition,
    FiscalizationTax,
    MasterpassCardResponse,
    MasterpassData,
    MasterpassDeleteCardRequest,
    MasterpassDeleteCardResponse,
    MasterpassGetCardRequest,
    MasterpassGetCardsRequest,
    MasterpassGetCardsResponse,
    MasterpassGetSavedCardRequest,
    MasterpassLoginRequest,
    MasterpassLoginResponse,
    MasterpassParams,
    P2pRequest,
    PaymentRequest,
    PayoutAddress,
    PayoutCreditCard,
    PayoutCustomer,
    PayoutRequest,
    PlanItem,
    ProductCreateRequest,
    ProductUpdateRequest,
    ProofDocument,
    ProofRequest,
    RecipientTokenizationRequest,
    RefundRequest,
    ReportCountParams,
    ReportCountRequest,
    ReportListRequest,
    ReportParams,
    SplitAdditionalData,
    SplitCreditCard,
    SplitPaymentRequest,
    SubscriptionCreateRequest,
    TokenizationRequest,
    VoidRequest,
)

SHOP_ID = "363"
SECRET = "45454e083434aa37rfdfd"
AUTH = "Basic MzYzOjQ1NDU0ZTA4MzQzNGFhMzdyZmRmZA=="


class MockTransport(httpx.MockTransport):
    def __init__(self, handlers: dict[tuple[str, str], dict]) -> None:
        self.handlers = handlers
        super().__init__(self._handler)

    def _handler(self, request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.path)
        if key not in self.handlers:
            raise AssertionError(f"Unmocked request: {key}")
        spec = self.handlers[key]
        assert request.headers.get("authorization") == AUTH, "bad auth"
        if "expect_host" in spec:
            assert request.url.host == spec["expect_host"]
        if "expect_version" in spec:
            assert request.headers.get("x-api-version") == spec["expect_version"], (
                "bad api version"
            )
        if "expect_request_id" in spec:
            assert request.headers.get("requestid") == spec["expect_request_id"], (
                "bad request id"
            )
        if "expect_body" in spec:
            assert json.loads(request.content) == spec["expect_body"]
        return httpx.Response(
            spec.get("status", 200),
            json=spec.get("json"),
            request=request,
        )


def client(handlers: dict) -> BepaidClient:
    return BepaidClient(SHOP_ID, SECRET, transport=MockTransport(handlers))


def async_client(handlers: dict) -> AsyncBepaidClient:
    return AsyncBepaidClient(SHOP_ID, SECRET, transport=MockTransport(handlers))


MASTERPASS_CASES = [
    (
        "login",
        MasterpassLoginRequest,
        {"phone": "375291234567", "fingerprint": "device-1"},
        {"phone_check_date": "2026-09-17T10:00:00Z", "channel": 0, "test": False},
        {"session": "session-1", "is_otp_required": False, "user_status": 0},
        MasterpassLoginResponse,
    ),
    (
        "get_cards",
        MasterpassGetCardsRequest,
        {"session": "session-1"},
        {"test": False},
        {
            "card_list": [
                {
                    "card_holder": "Test User",
                    "token": "masterpass-token",
                    "date": "2026-09-17",
                    "expiry_date": "2030-12",
                    "pan_mask": "555555******4444",
                    "card_status": 0,
                    "is_recurring": False,
                    "card_name": "Test card",
                    "comment1": "one",
                    "comment2": "two",
                    "comment3": "three",
                }
            ]
        },
        MasterpassGetCardsResponse,
    ),
    (
        "get_card",
        MasterpassGetCardRequest,
        {"token": "masterpass-token", "amount": 100, "currency": "BYN"},
        {"session": "session-1", "test": False},
        {
            "credit_card": {
                "token": "gateway-token",
                "brand": "master",
                "last_4": "4444",
            },
            "recommendation": 0,
            "required": 0,
        },
        MasterpassCardResponse,
    ),
    (
        "get_saved_card",
        MasterpassGetSavedCardRequest,
        {"credit_card_token": "gateway-token", "amount": 100, "currency": "BYN"},
        {"session": "session-1", "test": False},
        {
            "credit_card": {
                "token": "gateway-token",
                "exp_month": 12,
                "exp_year": 2030,
            },
            "recommendation": 1,
            "required": 1,
        },
        MasterpassCardResponse,
    ),
    (
        "delete_card",
        MasterpassDeleteCardRequest,
        {"session": "session-1", "token": "masterpass-token"},
        {"test": False},
        {"status": "successful"},
        MasterpassDeleteCardResponse,
    ),
]


def masterpass_case(case: tuple, with_options: bool, outcome: str) -> tuple:
    route, request_type, required, optional, success, response_type = case
    body = {**required, **optional} if with_options else required.copy()
    payload = success
    if outcome == "error":
        payload = {"status": "failed", "error": "Invalid session", "error_code": 101}
        if route == "get_saved_card":
            payload = {"status": "failed", "message": "Saved card not found"}
    elif outcome == "empty":
        payload = {"card_list": []} if route == "get_cards" else {}
    handlers = {
        ("POST", f"/masterpass/{route}"): {
            "expect_host": "gateway.bepaid.by",
            "expect_version": "3",
            "expect_request_id": None,
            "expect_body": body,
            "json": payload,
        }
    }
    return request_type.model_validate(body), response_type, payload, handlers


@pytest.mark.parametrize("case", MASTERPASS_CASES, ids=[c[0] for c in MASTERPASS_CASES])
@pytest.mark.parametrize("with_options", [False, True])
@pytest.mark.parametrize("outcome", ["success", "error", "empty"])
def test_masterpass(case: tuple, with_options: bool, outcome: str) -> None:
    req, response_type, payload, handlers = masterpass_case(case, with_options, outcome)
    with client(handlers) as c:
        response = getattr(c, f"masterpass_{case[0]}")(req)
    assert isinstance(response, response_type)
    assert response.model_dump(exclude_none=True) == payload


@pytest.mark.parametrize("case", MASTERPASS_CASES, ids=[c[0] for c in MASTERPASS_CASES])
def test_masterpass_required_fields(case: tuple) -> None:
    _, request_type, required, _, _, _ = case
    for field in required:
        with pytest.raises(ValidationError) as exc:
            request_type.model_validate(
                {key: value for key, value in required.items() if key != field}
            )
        assert any(
            error["loc"] == (field,) and error["type"] == "missing"
            for error in exc.value.errors()
        )


@pytest.mark.parametrize("case", MASTERPASS_CASES, ids=[c[0] for c in MASTERPASS_CASES])
def test_masterpass_http_error(case: tuple) -> None:
    req, _, _, handlers = masterpass_case(case, False, "error")
    spec = handlers[("POST", f"/masterpass/{case[0]}")]
    spec.update(status=400, json={"message": "Invalid request"})
    with client(handlers) as c, pytest.raises(ApiError) as exc:
        getattr(c, f"masterpass_{case[0]}")(req)
    assert exc.value.status == 400
    assert exc.value.message == "Invalid request"


def masterpass_transaction_case(
    operation: str, status: str, result_status: str
) -> tuple:
    metadata = AdditionalData(
        contract=["recurring"],
        masterpass=MasterpassData(params=MasterpassParams(session="session-1")),
    )
    body = {
        "amount": "100" if operation == "payment" else 100,
        "currency": "BYN",
        "description": "Masterpass payment",
        "tracking_id": "masterpass-1",
        "test": True,
        "credit_card": {"token": "gateway-token"},
        "additional_data": {
            "contract": ["recurring"],
            "masterpass": {"params": {"session": "session-1"}},
        },
    }
    request_type = PaymentRequest if operation == "payment" else AuthorizationRequest
    req = request_type.model_validate({**body, "additional_data": metadata})
    response_type = models.Transaction
    additional_data = {
        "contract": ["recurring"],
        "masterpass": {
            "params": {"session": "session-1"},
            "result": {
                "status": result_status,
                "error_code": 0,
                "details": {"unknown": [False, None]},
            },
        },
        "other": {"preserved": True},
    }
    handlers = {
        ("POST", f"/transactions/{operation}s"): {
            "expect_version": "3",
            "expect_body": {"request": body},
            "json": {
                "transaction": {
                    "uid": "mp-1",
                    "status": status,
                    "additional_data": additional_data,
                }
            },
        }
    }
    return req, response_type, additional_data, handlers


@pytest.mark.parametrize("operation", ["payment", "authorization"])
@pytest.mark.parametrize("status", ["successful", "failed"])
@pytest.mark.parametrize("result_status", ["successful", "failed"])
def test_masterpass_transaction_metadata(
    operation: str, status: str, result_status: str
) -> None:
    req, response_type, additional_data, handlers = masterpass_transaction_case(
        operation, status, result_status
    )
    with client(handlers) as c:
        response = getattr(c, f"create_{operation}")(req)
    assert isinstance(response, response_type)
    assert response.additional_data == additional_data
    assert response.model_dump()["additional_data"] == additional_data
    assert response.status == status


def _payment_request() -> PaymentRequest:
    return PaymentRequest(
        amount="700",
        currency="USD",
        test=True,
        description="Test transaction",
        tracking_id="tracking_id_000",
        duplicate_check=False,
    )


def test_create_payment_happy_path() -> None:
    c = client(
        {
            ("POST", "/transactions/payments"): {
                "expect_version": "3",
                "json": {
                    "transaction": {"tracking_id": "tracking_id_000", "uid": "u1"}
                },
            }
        }
    )
    resp = c.create_payment(_payment_request())
    assert resp.uid == "u1"


@pytest.mark.parametrize(
    "card",
    [
        {"token": "saved-card-token"},
        {"token": "$begateway_google_pay_1_0_0$eyJ0ZXN0Ijp0cnVlfQ=="},
        {"token": "$begateway_google_pay_decrypted_1_0_0$eyJ0ZXN0Ijp0cnVlfQ=="},
        {"token": "$begateway_samsung_pay_decrypted_1_0_0$eyJ0ZXN0Ijp0cnVlfQ=="},
        {
            "number": "4242424242424242",
            "verification_value": "123",
            "holder": "John Smith",
            "exp_month": 10,
            "exp_year": 2030,
        },
    ],
)
def test_create_payment_serializes_card(card: dict) -> None:
    req = _payment_request()
    req.credit_card = CreditCardRaw(**card)
    with client(
        {
            ("POST", "/transactions/payments"): {
                "expect_version": "3",
                "expect_body": {
                    "request": {
                        "amount": "700",
                        "currency": "USD",
                        "test": True,
                        "description": "Test transaction",
                        "tracking_id": "tracking_id_000",
                        "duplicate_check": False,
                        "credit_card": card,
                    }
                },
                "json": {"transaction": {"uid": "u1"}},
            }
        }
    ) as c:
        assert c.create_payment(req).uid == "u1"


def test_create_payment_sends_request_id() -> None:
    c = client(
        {
            ("POST", "/transactions/payments"): {
                "expect_version": "3",
                "expect_request_id": "uuid-request-1",
                "json": {"transaction": {"tracking_id": "t1", "uid": "u1"}},
            }
        }
    )
    resp = c.create_payment(_payment_request(), request_id="uuid-request-1")
    assert resp.uid == "u1"


def test_sync_reuses_persistent_client() -> None:
    handlers = {
        ("POST", "/transactions/payments"): {
            "expect_version": "3",
            "json": {"transaction": {"uid": "u1"}},
        }
    }
    c = client(handlers)
    c.create_payment(_payment_request())
    c.create_payment(_payment_request())
    assert c._async is not None
    assert c._loop is not None
    assert not c._loop.is_closed()
    first = c._async
    c.create_payment(_payment_request())
    assert c._async is first
    c.close()
    assert c._loop is None
    assert c._async is None
    with client(handlers) as cm:
        assert cm.create_payment(_payment_request()).uid == "u1"


def test_create_payment_serializes_request() -> None:
    c = client(
        {
            ("POST", "/transactions/payments"): {
                "expect_version": "3",
                "json": {"transaction": {"uid": "u1"}},
                "expect_body": {
                    "request": {
                        "amount": "700",
                        "currency": "USD",
                        "test": True,
                        "description": "Test transaction",
                        "tracking_id": "tracking_id_000",
                        "duplicate_check": False,
                    }
                },
            }
        }
    )
    c.create_payment(_payment_request())


def test_api_error_preserves_structured_details() -> None:
    payload = {
        **VISA_ALIAS_ERRORS[0][1],
        "errors": {"phone_number": ["is invalid"]},
    }
    with (
        client(
            {("POST", "/transactions/payments"): {"status": 400, "json": payload}}
        ) as c,
        pytest.raises(ApiError) as exc,
    ):
        c.create_payment(_payment_request())
    assert exc.value.message == payload["message"]
    assert exc.value.errors == payload["errors"]
    assert exc.value.error_code == "request_validation_error"
    assert exc.value.code == "E.1025"
    assert exc.value.friendly_message == "Invalid request params"
    legacy = ApiError(400, "Validation failed", {"amount": ["can't be blank"]})
    assert str(legacy) == "API error 400: Validation failed"
    assert legacy.errors == {"amount": ["can't be blank"]}
    assert legacy.error_code is None


def test_api_error_raises() -> None:
    c = client(
        {
            ("POST", "/transactions/payments"): {
                "expect_version": "3",
                "status": 400,
                "json": {
                    "message": "Validation failed",
                    "errors": {"amount": ["can't be blank"]},
                },
            }
        }
    )
    with pytest.raises(ApiError) as exc:
        c.create_payment(_payment_request())
    assert exc.value.status == 400
    assert exc.value.errors == {"amount": ["can't be blank"]}


def test_create_payment_serializes_h2h_fields() -> None:
    c = client(
        {
            ("POST", "/transactions/payments"): {
                "expect_version": "3",
                "json": {"transaction": {"uid": "u1"}},
                "expect_body": {
                    "request": {
                        "amount": "700",
                        "currency": "USD",
                        "test": True,
                        "description": "Test transaction",
                        "tracking_id": "tracking_id_000",
                        "return_url": "https://example.com/return",
                        "verification_url": "https://example.com/verify",
                    }
                },
            }
        }
    )
    c.create_payment(
        PaymentRequest(
            amount="700",
            currency="USD",
            test=True,
            description="Test transaction",
            tracking_id="tracking_id_000",
            return_url="https://example.com/return",
            verification_url="https://example.com/verify",
        )
    )


def test_create_payment_serializes_fiscalization_and_encrypted_data() -> None:
    c = client(
        {
            ("POST", "/transactions/payments"): {
                "expect_version": "3",
                "json": {"transaction": {"uid": "u1"}},
                "expect_body": {
                    "request": {
                        "amount": "700",
                        "currency": "USD",
                        "test": True,
                        "description": "Test transaction",
                        "tracking_id": "tid",
                        "encrypted_data": "jwe-blob",
                        "fiscalization": {
                            "external_id": "fisc-1",
                            "positions": [
                                {
                                    "name": "Product",
                                    "type": "service",
                                    "amount": 100,
                                    "quantity": 1.0,
                                    "measure_unit_code": 796,
                                    "description": "Desc",
                                    "untaxed": False,
                                    "nomenclature_code": "code-1",
                                    "taxes": [
                                        {
                                            "id": "vat-12",
                                            "percent": "12",
                                            "type": "vat",
                                            "inclusive": True,
                                        }
                                    ],
                                }
                            ],
                        },
                    }
                },
            }
        }
    )
    c.create_payment(
        PaymentRequest(
            amount="700",
            currency="USD",
            test=True,
            description="Test transaction",
            tracking_id="tid",
            encrypted_data="jwe-blob",
            fiscalization=Fiscalization(
                external_id="fisc-1",
                positions=[
                    FiscalizationPosition(
                        name="Product",
                        type="service",
                        amount=100,
                        quantity=1.0,
                        measure_unit_code=796,
                        description="Desc",
                        untaxed=False,
                        nomenclature_code="code-1",
                        taxes=[
                            FiscalizationTax(
                                id="vat-12", percent="12", type="vat", inclusive=True
                            )
                        ],
                    )
                ],
            ),
        )
    )


def test_create_payment_serializes_custom_fields() -> None:
    c = client(
        {
            ("POST", "/transactions/payments"): {
                "expect_version": "3",
                "json": {"transaction": {"uid": "u1"}},
                "expect_body": {
                    "request": {
                        "amount": "700",
                        "currency": "USD",
                        "test": True,
                        "description": "Test transaction",
                        "tracking_id": "tid",
                        "custom_fields": {
                            "custom_field_1": {
                                "label": "Email",
                                "value": "john@example.com",
                                "visible": True,
                                "required": True,
                            },
                            "custom_field_2": {
                                "label": "Agreement number",
                                "value": "12349",
                                "read_only": True,
                                "visible": True,
                            },
                        },
                    }
                },
            }
        }
    )
    c.create_payment(
        PaymentRequest(
            amount="700",
            currency="USD",
            test=True,
            description="Test transaction",
            tracking_id="tid",
            custom_fields=CustomFields(
                custom_field_1=CustomField(
                    label="Email",
                    value="john@example.com",
                    visible=True,
                    required=True,
                ),
                custom_field_2=CustomField(
                    label="Agreement number",
                    value="12349",
                    read_only=True,
                    visible=True,
                ),
            ),
        )
    )


@pytest.mark.parametrize(
    "token",
    [
        "saved-card-token",
        "$begateway_google_pay_1_0_0$eyJ0ZXN0Ijp0cnVlfQ==",
        "$begateway_google_pay_decrypted_1_0_0$eyJ0ZXN0Ijp0cnVlfQ==",
        "$begateway_samsung_pay_decrypted_1_0_0$eyJ0ZXN0Ijp0cnVlfQ==",
    ],
)
def test_create_authorization_returns_redirect(token: str) -> None:
    c = client(
        {
            ("POST", "/transactions/authorizations"): {
                "expect_version": "3",
                "expect_body": {
                    "request": {
                        "amount": 100,
                        "currency": "USD",
                        "description": "Test",
                        "tracking_id": "x",
                        "duplicate_check": False,
                        "credit_card": {"token": token},
                        "additional_data": {"contract": ["recurring"]},
                    }
                },
                "json": {
                    "transaction": {
                        "uid": "b6c446e4",
                        "status": "incomplete",
                        "redirect_url": "https://gateway.bepaid.by/process/b6c446e4",
                        "three_d_secure_verification": {
                            "status": "incomplete",
                            "message": "Authentication Available",
                            "pa_res_url": "https://gateway.bepaid.by/process/b6c446e4",
                        },
                    }
                },
            }
        }
    )
    resp = c.create_authorization(
        AuthorizationRequest(
            amount=100,
            currency="USD",
            description="Test",
            tracking_id="x",
            duplicate_check=False,
            credit_card=CreditCardRaw(token=token),
            additional_data=AdditionalData(contract=["recurring"]),
        )
    )
    assert resp.status == "incomplete"
    assert resp.redirect_url is not None
    assert resp.redirect_url.endswith("/process/b6c446e4")
    assert resp.three_d_secure_verification is not None


def test_capture_and_void() -> None:
    c = client(
        {
            ("POST", "/transactions/captures"): {
                "expect_version": "3",
                "json": {
                    "transaction": {
                        "uid": "c1",
                        "status": "successful",
                        "type": "capture",
                        "parent_uid": "p1",
                    }
                },
            },
            ("POST", "/transactions/voids"): {
                "expect_version": "3",
                "json": {
                    "transaction": {
                        "uid": "v1",
                        "status": "successful",
                        "type": "void",
                    }
                },
            },
        }
    )
    cap = c.capture(CaptureRequest(parent_uid="p1", amount=50))
    assert cap.status == "successful"
    v = c.void(VoidRequest(parent_uid="p1", amount=50))
    assert v.status == "successful"


def test_refund() -> None:
    c = client(
        {
            ("POST", "/transactions/refunds"): {
                "expect_version": "3",
                "json": {
                    "transaction": {
                        "uid": "r1",
                        "parent_uid": "p1",
                        "type": "refund",
                        "status": "successful",
                    }
                },
            }
        }
    )
    resp = c.refund(RefundRequest(parent_uid="p1", amount=50, reason="Client request"))
    assert resp.status == "successful"
    assert resp.type == "refund"


def test_charge_saved_card() -> None:
    c = client(
        {
            ("POST", "/services/credit_cards/charges"): {
                "expect_version": "3",
                "json": {
                    "transaction": {
                        "uid": "1-310b0da80b",
                        "type": "payment",
                        "status": "successful",
                        "amount": 700,
                        "currency": "USD",
                        "test": True,
                        "credit_card": {
                            "last_4": "1006",
                            "brand": "visa",
                        },
                    }
                },
            }
        }
    )
    resp = c.charge_saved_card(
        ChargeRequest(
            amount=700,
            currency="USD",
            description="Saved card charge",
            credit_card=ChargeCreditCard(token="tok_123"),
        )
    )
    assert resp.uid == "1-310b0da80b"
    assert resp.status == "successful"


def test_recipient_tokenization() -> None:
    c = client(
        {
            ("POST", "/transactions/recipient_tokenizations"): {
                "expect_version": "3",
                "json": {
                    "transaction": {
                        "uid": "1-310b0da80b",
                        "status": "pending",
                        "recipient_credit_card": {"token": "tok_recipient"},
                    }
                },
            }
        }
    )
    resp = c.tokenize_recipient_card(
        RecipientTokenizationRequest(
            description="Tokenize card",
            recipient_credit_card=PayoutCreditCard(
                number="4242424242424242", holder="John Smith"
            ),
        )
    )
    assert resp["transaction"]["uid"] == "1-310b0da80b"
    assert resp["transaction"]["status"] == "pending"


def test_apple_pay_payment() -> None:
    c = client(
        {
            ("POST", "/apple_pay/payment"): {
                "json": {"Success": True, "Model": None},
            }
        }
    )
    resp = c.apple_pay_payment("eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9...")
    assert resp["Success"] is True


def test_get_transaction() -> None:
    c = client(
        {
            ("GET", "/transactions/2f4d67ff"): {
                "json": {
                    "transaction": {
                        "uid": "2f4d67ff",
                        "status": "successful",
                        "code": "S.0000",
                        "credit_card": {"brand": "visa", "last_4": "1097"},
                        "payment": {"auth_code": "654321", "status": "successful"},
                    }
                }
            }
        }
    )
    t = c.get_transaction("2f4d67ff")
    assert t.status == "successful"
    assert t.code == "S.0000"
    assert t.credit_card is not None
    assert t.credit_card.brand == "visa"


def test_transaction_status_by_tracking_id() -> None:
    c = client(
        {
            ("GET", "/v2/transactions/tracking_id/order-123"): {
                "json": {
                    "uid": "54c70f9b-e6e5-4b5a-bda2-fe6980e44bf0",
                    "transaction_status": "approved",
                    "result_code": "0",
                    "cvc_verification": {"result_code": "1"},
                    "billing_address": {"city": "Denver"},
                }
            }
        }
    )
    t = c.get_transaction_by_tracking_id("order-123")
    assert t.uid == "54c70f9b-e6e5-4b5a-bda2-fe6980e44bf0"
    assert t.transaction_status == "approved"
    assert t.cvc_verification is not None
    assert t.cvc_verification.result_code == "1"
    assert t.billing_address is not None
    assert t.billing_address.city == "Denver"


def test_create_token() -> None:
    c = client(
        {
            ("POST", "/credit_cards"): {
                "expect_version": "3",
                "json": {
                    "holder": "John Doe",
                    "brand": "visa",
                    "last_4": "0000",
                    "token": "7ba647e7013b5cb9df39f17c375783aef",
                    "exp_month": 1,
                    "exp_year": 2028,
                },
            }
        }
    )
    t = c.create_token(
        CreateTokenRequest(
            number="4200000000000000",
            holder="John Doe",
            exp_month="05",
            exp_year="2028",
            contract=["recurring"],
        )
    )
    assert t.brand == "visa"


def test_create_tokenization() -> None:
    c = client(
        {
            ("POST", "/transactions/tokenizations"): {
                "expect_version": "3",
                "json": {
                    "transaction": {
                        "uid": "e89abc1a-1d18-4d0f-83a1-7009b333dce0",
                        "status": "successful",
                        "type": "tokenization",
                        "credit_card": {
                            "brand": "visa",
                            "last_4": "1097",
                            "token": "e3ba5977-8705-4496-bf90-a6a93d3d31cc",
                        },
                        "tokenization": {
                            "gateway_id": 3483,
                            "status": "successful",
                        },
                    }
                },
            }
        }
    )
    t = c.create_tokenization(
        TokenizationRequest(
            amount=100,
            currency="USD",
            description="Test transaction",
            test=True,
            credit_card=CreditCardRaw(
                number="4200000000000000",
                verification_value="123",
                holder="John Doe",
                exp_month=5,
                exp_year=2028,
            ),
        )
    )
    assert t.uid == "e89abc1a-1d18-4d0f-83a1-7009b333dce0"
    assert (
        t.credit_card is not None
        and t.credit_card.token == "e3ba5977-8705-4496-bf90-a6a93d3d31cc"
    )
    assert t.tokenization is not None and t.tokenization["status"] == "successful"


def test_checkout_create_and_status() -> None:
    c = client(
        {
            ("POST", "/ctp/api/checkouts"): {
                "json": {
                    "checkout": {
                        "token": "tok1",
                        "redirect_url": "https://checkout.bepaid.by/widget/hpp.html?token=tok1",
                    }
                }
            },
            ("GET", "/ctp/api/checkouts/tok1"): {
                "json": {"checkout": {"token": "tok1", "shop_id": 160}}
            },
        }
    )
    co = c.create_checkout(
        CheckoutRequest(
            test=True,
            order=CheckoutOrder(currency="USD", amount=7000, description="Test"),
        )
    )
    assert co.token == "tok1"
    st = c.get_checkout_status("tok1")
    assert st.shop_id == 160


def test_payment_token_happy_path() -> None:
    c = client(
        {
            ("POST", "/payments/tokens"): {
                "json": {
                    "checkout": {
                        "token": "3241e439f8c87d941d92621a4bdc030d",
                        "redirect_url": "https://checkout.bepaid.by/v2/checkout?token=3241e439f8c87d941d92621a4bdc030d",
                    }
                }
            }
        }
    )
    p = c.create_payment_token(
        CheckoutRequest(
            test=True,
            order=CheckoutOrder(
                currency="USD",
                amount=7000,
                description="Widget order",
                additional_data=CheckoutOrderAdditionalData(contract=["recurring"]),
            ),
        )
    )
    assert p.token == "3241e439f8c87d941d92621a4bdc030d"
    assert p.redirect_url and "checkout.bepaid.by/v2/checkout" in p.redirect_url


def test_apm_payment_and_refund() -> None:
    c = client(
        {
            ("POST", "/beyag/transactions/payments"): {
                "json": {
                    "transaction": {
                        "uid": "apm1",
                        "type": "payment",
                        "status": "pending",
                        "method_type": "mts_money",
                    }
                }
            },
            ("POST", "/beyag/transactions/refunds"): {
                "json": {
                    "transaction": {
                        "uid": "r1",
                        "type": "refund",
                        "status": "successful",
                    }
                }
            },
        }
    )
    p = c.create_apm_payment(
        ApmPaymentRequest(
            amount=100,
            currency="BYN",
            ip="127.0.0.1",
            payment_method={"type": "mts_money", "confirm_agreement": "accept"},
        )
    )
    assert p.status == "pending"
    r = c.apm_refund(ApmRefundRequest(parent_uid="apm1", reason="reason"))
    assert r.status == "successful"


ERIP_PAYMENT = {
    "uid": "erip-1",
    "id": "erip-1",
    "status": "pending",
    "type": "payment",
    "amount": 0,
    "currency": "BYN",
    "description": "Meter payment",
    "order_id": "123456789012",
    "tracking_id": "order-1",
    "payment_method_type": "erip",
    "language": "ru",
    "test": False,
    "version": 0,
    "created_at": "2026-09-17T10:00:00Z",
    "updated_at": "2026-09-17T10:00:01Z",
    "expired_at": "2026-09-18T10:00:00Z",
    "paid_at": "2026-09-17T10:00:02Z",
    "closed_at": "2026-09-17T10:00:03Z",
    "settled_at": "2026-09-17T10:00:04Z",
    "psp_settled_at": None,
    "registry_id": None,
    "manually_corrected_at": "2026-09-17T10:00:05Z",
    "customer": {"ip": "127.0.0.1", "email": None, "middle_name": "Ivanovich"},
    "billing_address": {"first_name": "Ivan", "middle_name": "Ivanovich"},
    "additional_data": {"notifications": ["sms"], "receipt_text": ["Thank you"]},
    "payment": {"gateway_id": 3483, "status": "pending", "ref_id": None},
    "erip": {
        "request_id": "00001",
        "transaction_id": 42,
        "service_no": 99999999,
        "service_no_erip": "12345678",
        "account_number": "123",
        "instruction": ["Payments -> Shop"],
        "service_info": ["Meter payment"],
        "receipt": ["Thank you"],
        "qr_code_raw": "dGVzdA==",
        "qr_code": "data:image/png;base64,dGVzdA==",
        "banks": [{"name": "Bank", "platform_urls": {"ios": "bank://pay#"}}],
    },
}

ERIP_REFUND = {
    "uid": "refund-1",
    "id": "refund-1",
    "parent_uid": "erip-1",
    "type": "refund",
    "status": "successful",
    "message": "Updated manually",
    "amount": 50,
    "currency": "BYN",
    "reason": "Client request",
    "created_at": "2026-09-17T10:00:00Z",
    "paid_at": "2026-09-17T10:00:01Z",
    "test": False,
    "language": "ru",
    "version": 2,
    "settled_at": None,
    "psp_settled_at": None,
    "registry_id": None,
    "payment_method_type": "erip",
    "erip": {"service_no": "6777"},
    "refund": {"ref_id": "8304334", "rrn": None, "status": "successful"},
}

ERIP_CASES = [
    "create_erip_payment",
    "create_apm_payment",
    "apm_full_refund",
    "get_apm_refund",
    "tree_list",
    "tree_object",
    "create_authorization",
    "create_checkout",
    "create_payment_token",
]


def erip_case(case: str) -> tuple:
    operation = case
    method = "POST"
    host = "api.bepaid.by"
    version = None
    request_id = None
    if case in ("create_erip_payment", "create_apm_payment"):
        body = {
            "amount": 0,
            "currency": "BYN",
            "description": "Meter payment",
            "ip": "127.0.0.1",
            "payment_method": {
                "type": "erip",
                "account_number": "123",
                "service_no": "99999999",
                "service_info": ["Meter payment"],
                "erip_devices": [
                    {
                        "name": "Water",
                        "item_unit": "m3",
                        "rank": "4",
                        "value": "1234",
                        "rate": "0.4392",
                    }
                ],
            },
            "customer": {"middle_name": "Ivanovich"},
            "additional_data": {"notifications": ["sms"]},
        }
        args = (ApmPaymentRequest.model_validate(body), "erip-request-1")
        request_id = "erip-request-1"
        path = (
            "/beyag/payments"
            if case == "create_erip_payment"
            else "/beyag/transactions/payments"
        )
        if case == "create_apm_payment":
            body["method"] = body.pop("payment_method")
        body = {"request": body}
        payload = ERIP_PAYMENT
        response_type = models.ApmPaymentResponse
        response = {"transaction": payload}
    elif case in ("apm_full_refund", "get_apm_refund"):
        path = "/beyag/refunds"
        body = {
            "request": {
                "parent_uid": "erip-1",
                "reason": "Client request",
                "amount": 50,
            }
        }
        args = ("erip-1", "Client request", 50, "refund-request-1")
        request_id = "refund-request-1"
        if case == "get_apm_refund":
            method = "GET"
            path += "/refund-1"
            args = ("refund-1",)
            request_id = None
        payload = ERIP_REFUND
        response_type = models.ApmRefundResponse
        response = {"transaction": payload}
    elif case.startswith("tree_"):
        operation = "get_erip_pay_list"
        path = "/beyag/gateways/komplat/get_pay_list"
        body = {"terminal_id": "10000002", "pay_code": "11000000000", "di_type": "9191"}
        payload = [{"code": "11000304194", "name": "Services", "di_type": "9120"}]
        if case == "tree_object":
            body.update(
                test=False,
                erip_session_id="session-1",
                attributes={"1001": "0291234567"},
                customer={"personal_account": "123", "erip_account": "456"},
            )
            payload = {
                "code": "10004372291",
                "erip_session_id": "session-1",
                "billed_amount": "122.43",
                "fixed_amount": False,
                "customer_name": None,
                "required_attributes": [],
                "information_attributes": [{"name": "Debt", "value": None}],
            }
        args = (models.EripPayListRequest.model_validate(body),)
        response_type = list if case == "tree_list" else dict
        response = payload
    elif case == "create_authorization":
        host = "gateway.bepaid.by"
        version = "3"
        path = "/transactions/authorizations"
        body = {
            "amount": 100,
            "currency": "BYN",
            "description": "ERIP",
            "tracking_id": "order-1",
            "credit_card": {"token": "card-token"},
            "additional_data": {
                "komplat": {
                    "pay_code": "10000156731",
                    "di_type": "9191",
                    "erip_session_id": "session-1",
                }
            },
        }
        args = (AuthorizationRequest.model_validate(body),)
        body = {"request": body}
        payload = {"uid": "authorization-1"}
        response_type = models.Transaction
        response = {"transaction": payload}
    else:
        path = "/payments/tokens"
        if case == "create_checkout":
            version = "2"
            host = "checkout.bepaid.by"
            path = "/ctp/api/checkouts"
        body = {
            "transaction_type": "payment",
            "payment_method": {
                "types": ["credit_card", "bank_transfer"],
                "excluded_types": ["erip"],
                "bank_transfer": {"account": "DE89370400440532013000"},
            },
            "order": {
                "amount": 100,
                "currency": "BYN",
                "additional_data": {
                    "contract": ["recurring"],
                    "bank_transfer": {"reference": "order-1"},
                },
            },
        }
        args = (CheckoutRequest.model_validate(body),)
        body = {"checkout": body}
        payload = {"token": "checkout-1"}
        response_type = models.CheckoutResponse
        response = {"checkout": payload}
    spec = {
        "expect_host": host,
        "expect_version": version,
        "expect_request_id": request_id,
        "json": response,
    }
    if method == "POST":
        spec["expect_body"] = body
    return operation, args, payload, response_type, {(method, path): spec}


@pytest.mark.parametrize("case", ERIP_CASES)
def test_erip_contract(case: str) -> None:
    operation, args, payload, response_type, handlers = erip_case(case)
    with client(handlers) as c:
        response = getattr(c, operation)(*args)
    assert isinstance(response, response_type)
    assert (
        response
        if isinstance(response, (dict, list))
        else response.model_dump(exclude_unset=True)
    ) == payload


@pytest.mark.parametrize(
    "field,value",
    [
        ("currency", "USD"),
        ("description", None),
        ("ip", None),
        ("payment_method", {"type": "erip"}),
        ("payment_method", {"type": "mts_money", "account_number": "123"}),
        ("payment_method", {"type": "erip", "account_number": 123}),
    ],
)
def test_erip_rejects_invalid_request(field: str, value: object) -> None:
    body = {
        "amount": 0,
        "currency": "BYN",
        "description": "ERIP",
        "ip": "127.0.0.1",
        "payment_method": {"type": "erip", "account_number": "123"},
    }
    body[field] = value
    with client({}) as c, pytest.raises(ValueError):
        c.create_erip_payment(ApmPaymentRequest.model_validate(body))


def test_erip_refund_requires_amount() -> None:
    with client({}) as c, pytest.raises(ValueError, match="amount"):
        c.apm_full_refund("erip-1", "Client request")


def test_erip_tree_required_fields() -> None:
    body = {"terminal_id": "10000002", "pay_code": "11000000000", "di_type": "9191"}
    for field in body:
        with pytest.raises(ValidationError):
            models.EripPayListRequest.model_validate(
                {key: value for key, value in body.items() if key != field}
            )


@pytest.mark.parametrize(
    "payload",
    [
        ERIP_PAYMENT,
        ERIP_REFUND,
        {
            "uid": "external-1",
            "status": "successful",
            "method_type": "erip_external",
            "payment_method_type": "erip_external",
            "erip_external": {
                "account": "123",
                "service_no": "6777",
                "details": [False, None],
            },
            "bank_transfer": {"account": "123"},
        },
    ],
)
def test_erip_webhook_preserves_metadata(payload: dict) -> None:
    notification = parse_webhook(json.dumps({"transaction": payload}))
    assert notification.model_dump(exclude_unset=True) == {"transaction": payload}


def test_erip_transaction_billing_address() -> None:
    transaction = models.Transaction.model_validate(ERIP_PAYMENT)
    assert transaction.billing_address is not None
    assert transaction.billing_address.middle_name == "Ivanovich"
    assert transaction.customer is not None
    assert transaction.customer.middle_name == "Ivanovich"


def test_apm_payment_constructors_serialize() -> None:
    device = EripDevice(
        name="Холодная вода", item_unit="м3", rank="4", value="1234", rate="0.4392"
    )
    cases = [
        (
            ApmPaymentRequest.erip(1000, "BYN", "123", "99999999"),
            {
                "request": {
                    "amount": 1000,
                    "currency": "BYN",
                    "payment_method": {
                        "type": "erip",
                        "account_number": "123",
                        "service_no": "99999999",
                    },
                }
            },
        ),
        (
            ApmPaymentRequest.mts_money(100, "BYN", "375295222222", "accept"),
            {
                "request": {
                    "amount": 100,
                    "currency": "BYN",
                    "customer": {"phone": "375295222222"},
                    "payment_method": {
                        "type": "mts_money",
                        "confirm_agreement": "accept",
                    },
                }
            },
        ),
        (
            ApmPaymentRequest.krok(220, "BYN", "https://example.com/return"),
            {
                "request": {
                    "amount": 220,
                    "currency": "BYN",
                    "return_url": "https://example.com/return",
                    "payment_method": {"type": "krok"},
                }
            },
        ),
        (
            ApmPaymentRequest.qiwi_terminal(1000, "RUB", "test_account_123"),
            {
                "request": {
                    "amount": 1000,
                    "currency": "RUB",
                    "payment_method": {
                        "type": "qiwi_terminal",
                        "account": "test_account_123",
                    },
                }
            },
        ),
        (
            ApmPaymentRequest.sberpay(
                2200, "RUB", "https://return.example.com", "375291234567"
            ),
            {
                "request": {
                    "amount": 2200,
                    "currency": "RUB",
                    "return_url": "https://return.example.com",
                    "customer": {"phone": "375291234567"},
                    "payment_method": {"type": "sberpay_qr_deeplink"},
                }
            },
        ),
        (
            ApmPaymentRequest.sberpay(500, "BYN", "https://ret.example.com"),
            {
                "request": {
                    "amount": 500,
                    "currency": "BYN",
                    "return_url": "https://ret.example.com",
                    "payment_method": {"type": "sberpay_qr_deeplink"},
                }
            },
        ),
        (
            ApmPaymentRequest.alfaclick(120, "BYN"),
            {
                "request": {
                    "amount": 120,
                    "currency": "BYN",
                    "payment_method": {"type": "alfaclick"},
                }
            },
        ),
        (
            ApmPaymentRequest.webpay(130, "BYN"),
            {
                "request": {
                    "amount": 130,
                    "currency": "BYN",
                    "payment_method": {"type": "webpay"},
                }
            },
        ),
        (
            ApmPaymentRequest.rccard(140, "BYN"),
            {
                "request": {
                    "amount": 140,
                    "currency": "BYN",
                    "payment_method": {"type": "rccard"},
                }
            },
        ),
        (
            ApmPaymentRequest.byncard(150, "BYN"),
            {
                "request": {
                    "amount": 150,
                    "currency": "BYN",
                    "payment_method": {"type": "byncard"},
                }
            },
        ),
        (
            ApmPaymentRequest.halva(160, "BYN"),
            {
                "request": {
                    "amount": 160,
                    "currency": "BYN",
                    "payment_method": {"type": "halva"},
                }
            },
        ),
    ]
    for req, expected in cases:
        expected["request"]["method"] = expected["request"].pop("payment_method")
        c = client(
            {
                ("POST", "/beyag/transactions/payments"): {
                    "expect_body": expected,
                    "json": {"transaction": {"uid": "u", "status": "pending"}},
                }
            }
        )
        p = c.create_apm_payment(req)
        assert p.status == "pending"

    req = ApmPaymentRequest.erip(1000, "BYN", "123", "99999999", erip_devices=[device])
    c = client(
        {
            ("POST", "/beyag/transactions/payments"): {
                "expect_body": {
                    "request": {
                        "amount": 1000,
                        "currency": "BYN",
                        "method": {
                            "type": "erip",
                            "account_number": "123",
                            "service_no": "99999999",
                            "erip_devices": [
                                {
                                    "name": "Холодная вода",
                                    "item_unit": "м3",
                                    "rank": "4",
                                    "value": "1234",
                                    "rate": "0.4392",
                                }
                            ],
                        },
                    }
                },
                "json": {"transaction": {"uid": "u", "status": "pending"}},
            }
        }
    )
    assert c.create_apm_payment(req).status == "pending"


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (AUTH, True),
        ("Basic bm90OnJpZ2h0", False),
    ],
)
def test_verify_webhook_auth(header: str, expected: bool) -> None:
    assert verify_webhook_auth(header, SHOP_ID, SECRET) is expected


def test_verify_webhook_signature() -> None:
    import base64

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key_pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    body = b'{"transaction":{"uid":"123"}}'
    signature = base64.b64encode(
        key.sign(body, padding.PKCS1v15(), hashes.SHA256())
    ).decode()

    assert verify_webhook_signature(public_key_pem, signature, body) is True
    assert verify_webhook_signature(public_key_pem, signature, b"tampered") is False


def test_parse_webhook() -> None:
    notification = parse_webhook('{"transaction":{"uid":"123","status":"successful"}}')
    assert notification.transaction.uid == "123"
    assert notification.transaction.status == "successful"


def test_parse_subscription_webhook() -> None:
    subscription = parse_subscription_webhook('{"state":"active","currency":"USD"}')
    assert subscription.state == "active"


def test_parse_checkout_webhook() -> None:
    status = parse_checkout_webhook(
        '{"token":"tok123","status":"error","expired":true,"finished":false,'
        '"message":"Token is expired.","shop_id":363}'
    )
    assert status.token == "tok123"
    assert status.status == "error"
    assert status.expired is True
    assert status.finished is False
    assert status.message == "Token is expired."


def test_get_plan_payment_link() -> None:
    c = client(
        {
            ("GET", "/plans/pln_a134847c902551de/pay"): {
                "json": {"redirect_url": "https://checkout.bepaid.by/pay?token=abc"}
            }
        }
    )
    link = c.get_plan_payment_link("pln_a134847c902551de")
    assert link["redirect_url"] == "https://checkout.bepaid.by/pay?token=abc"


def test_errors_baseclass() -> None:
    assert issubclass(ApiError, BepaidError)


APM_BATCH7_CASES = [
    "generic",
    "erip",
    "confirm",
    "cancel",
    "legacy",
    "sberpay",
    "mts_v2_true",
    "mts_v2_false",
    "mts_v2_null",
    "mts_v3",
    "qiwi_empty",
    "qiwi_message",
    "qiwi_error",
]


def apm_batch7_case(case: str) -> tuple:
    path = "/beyag/transactions/payments"
    version = None
    request_id = None
    payload = {"uid": "apm-7", "status": "pending"}
    response = {"transaction": payload}
    status = 200
    if case in ("generic", "erip"):
        req = ApmPaymentRequest(
            amount=100,
            currency="BYN",
            description="Invoice",
            ip="127.0.0.1",
            payment_method={"type": "erip", "account_number": "123"},
        )
        operation = "create_apm_payment" if case == "generic" else "create_erip_payment"
        if case == "erip":
            path = "/beyag/payments"
        body = {
            "request": {
                "amount": 100,
                "currency": "BYN",
                "description": "Invoice",
                "ip": "127.0.0.1",
                "method" if case == "generic" else "payment_method": {
                    "type": "erip",
                    "account_number": "123",
                },
            }
        }
        request_id = "batch7"
        args = (req, request_id)
    elif case in ("confirm", "cancel", "legacy", "sberpay"):
        operation = "confirm_apm_payment"
        path = "/beyag/transactions/apm-7/confirm"
        fields = {"confirm_type": case}
        if case == "legacy":
            fields = {
                "transaction_reference": "receipt-7",
                "skip_duplicate_check": False,
            }
        elif case == "sberpay":
            fields = {"phone": "+79123456789"}
        args = ("apm-7", ApmConfirmRequest.model_validate(fields), "batch7")
        request_id = "batch7"
        body = fields if case == "sberpay" else {"request": fields}
        payload = {
            "parent_uid": "apm-7",
            "type": "confirm",
            "status": "successful",
            "message": "Processed",
            "created_at": "2026-04-07T13:04:31.189+00:00",
            "amount": 6500,
            "currency": "BYN",
        }
        response = {
            "transaction" if case in ("confirm", "cancel") else "response": payload
        }
    elif case.startswith("mts_"):
        operation = "check_mts_service" if case == "mts_v3" else "check_mts_service_v2"
        path = (
            "/beyag/gateways/mts_money_widget/check_service"
            if case == "mts_v3"
            else "/beyag/gateways/mts_money/check_service"
        )
        version = "3" if case == "mts_v3" else "2"
        args = ("375295222222",)
        body = {
            "request": {
                "customer": {"phone": "375295222222"},
                **({"test": False} if case != "mts_v2_null" else {}),
            }
        }
        payload = {
            "service_activated": True
            if case in ("mts_v2_true", "mts_v3")
            else False
            if case == "mts_v2_false"
            else None,
            "message": "Service check",
            "validation": {"operator": "mts", "message": "OK"},
        }
        if case == "mts_v2_null":
            payload["error_code"] = "invalid_phone"
        response = payload
    else:
        operation = "test_qiwi_terminal_payment"
        path = "/beyag/testing/payment"
        args = (1000, "RUB", "test_account_123")
        body = {
            "request": {
                "amount": 1000,
                "currency": "RUB",
                "method": {"type": "qiwi_terminal", "account": "test_account_123"},
                "test": True,
            }
        }
        payload = {} if case == "qiwi_empty" else {"message": "4 Wrong account format"}
        response = None if case == "qiwi_empty" else payload
        if case == "qiwi_error":
            status = 400
    spec = {
        "expect_host": "api.bepaid.by",
        "expect_version": version,
        "expect_request_id": request_id,
        "expect_body": body,
        "json": response,
        "status": status,
    }
    kwargs = (
        {"test": False} if case.startswith("mts_") and case != "mts_v2_null" else {}
    )
    return operation, args, kwargs, payload, {("POST", path): spec}


@pytest.mark.parametrize("case", APM_BATCH7_CASES)
def test_apm_batch7_contract(case: str) -> None:
    operation, args, kwargs, payload, handlers = apm_batch7_case(case)
    with client(handlers) as c:
        if case == "qiwi_error":
            with pytest.raises(ApiError) as exc:
                getattr(c, operation)(*args, **kwargs)
            assert exc.value.status == 400
            assert exc.value.message == payload["message"]
            return
        result = getattr(c, operation)(*args, **kwargs)
    assert (
        result if isinstance(result, dict) else result.model_dump(exclude_unset=True)
    ) == payload
    if case in ("generic", "erip"):
        assert args[0].payment_method == {"type": "erip", "account_number": "123"}


APM_METHOD_RESULTS = [
    {
        "krok": {
            "qr_code": "data:image/png;base64,dGVzdA==",
            "banks": [{"name": "Bank", "platform_urls": {"ios": "bank://pay"}}],
        }
    },
    {"pix": {"hash": "pix-hash"}},
    {"crypto_currency": {"amount": "0.00001000", "wallet": "wallet-7"}},
    {"sbp": {"token": "sbp-token"}},
    {"sberpay_qr_deeplink": {"qr_code": "dGVzdA==", "deep_link": "sberpay://invoice"}},
    {"form": {"action": "sberpay://invoice", "method": "GET", "fields": []}},
    {"form": "<form></form>"},
]


@pytest.mark.parametrize("details", APM_METHOD_RESULTS)
@pytest.mark.parametrize(
    "operation",
    [
        "create_apm_payment",
        "get_apm_transaction",
        "get_apm_transactions_by_tracking_id",
    ],
)
def test_apm_batch7_method_results(details: dict, operation: str) -> None:
    payload = {"uid": "apm-7", "status": "pending", **details}
    path = "/beyag/transactions/apm-7"
    method = "GET"
    args = ("apm-7",)
    response = {"transaction": payload}
    if operation == "create_apm_payment":
        method, path = "POST", "/beyag/transactions/payments"
        args = (ApmPaymentRequest.krok(100, "BYN", "https://example.com/return"),)
    elif operation == "get_apm_transactions_by_tracking_id":
        path = "/beyag/transactions/tracking_id/apm-7"
        response = {"transactions": [payload]}
    with client({(method, path): {"json": response}}) as c:
        result = getattr(c, operation)(*args)
    if isinstance(result, list):
        result = result[0]
    assert result.model_dump(exclude_unset=True) == payload


@pytest.mark.parametrize(
    "fields",
    [
        {"confirm_type": "unknown"},
        {"confirm_type": "confirm", "transaction_reference": "receipt"},
        {"confirm_type": "cancel", "phone": "+79123456789"},
        {"phone": "+79123456789", "transaction_reference": "receipt"},
        {"phone": "+79123456789", "skip_duplicate_check": False},
        {"confirm_type": "confirm", "skip_duplicate_check": False},
    ],
)
def test_apm_batch7_rejects_mixed_or_invalid_confirm_mode(fields: dict) -> None:
    with client({}) as c, pytest.raises(ValueError):
        c.confirm_apm_payment("apm-7", ApmConfirmRequest.model_validate(fields))


def test_apm_batch7_customer_fields() -> None:
    req = ApmPaymentRequest(
        amount=100,
        currency="BYN",
        payment_method={"type": "pix"},
        customer=models.Customer.model_validate(
            {"gender": "male", "street": "Main Street"}
        ),
    )
    with client(
        {
            ("POST", "/beyag/transactions/payments"): {
                "expect_body": {
                    "request": {
                        "amount": 100,
                        "currency": "BYN",
                        "method": {"type": "pix"},
                        "customer": {"gender": "male", "street": "Main Street"},
                    }
                },
                "json": {"transaction": {"uid": "apm-7"}},
            }
        }
    ) as c:
        c.create_apm_payment(req)
    assert models.Customer().model_dump(exclude_none=True) == {}


def test_apm_confirm() -> None:
    c = client(
        {
            ("POST", "/beyag/transactions/1-310b0da80b/confirm"): {
                "json": {
                    "response": {
                        "parent_uid": "1-310b0da80b",
                        "type": "confirm",
                        "status": "successful",
                        "message": "Confirm was successfully processed",
                        "amount": 332400,
                        "currency": "USD",
                    }
                }
            }
        }
    )
    resp = c.confirm_apm_payment(
        "1-310b0da80b",
        ApmConfirmRequest(
            skip_duplicate_check=False, transaction_reference="receipt-123"
        ),
    )
    assert resp.status == "successful"
    assert resp.type == "confirm"


VISA_ALIAS_SUCCESS = {
    "holder": "Test Recipient",
    "stamp": "card-stamp",
    "brand": "visa",
    "last_4": "0000",
    "first_1": "4",
    "bin": "420000",
    "bin_8": "42000000",
    "issuer_country": "BY",
    "issuer_name": "Test Bank",
    "product": "Visa Classic",
    "exp_month": 12,
    "exp_year": 2030,
    "token_provider": "visa",
    "token": "visa-alias-token",
    "service_info": {
        "recipientName": "Test Recipient",
        "issuerName": "Test Bank",
        "cardType": "Debit",
        "address1": "1 Test Street",
        "address2": "Unit 2",
        "city": "Minsk",
        "country": "BY",
        "postalCode": "220000",
    },
}

VISA_ALIAS_ERRORS = [
    (
        400,
        {
            "error_code": "request_validation_error",
            "message": {"recipient_info": {"phone_number": ["is in invalid format"]}},
            "status": "error",
            "code": "E.1025",
            "friendly_message": "Invalid request params",
        },
    ),
    (
        404,
        {
            "status": "error",
            "code": "E.1037",
            "message": "Card Not Found",
            "friendly_message": "Card Not Found",
        },
    ),
]


def visa_alias_case(payload: dict, status: int = 200) -> tuple:
    req = models.VisaAliasPhoneRequest(
        recipient_info=models.VisaAliasRecipientInfo(phone_number="375291234567")
    )
    handlers = {
        ("POST", "/services/visa-alias/verify-phone"): {
            "expect_host": "gateway.bepaid.by",
            "expect_version": "3",
            "expect_body": {"recipient_info": {"phone_number": "375291234567"}},
            "status": status,
            "json": payload,
        }
    }
    return req, handlers


def test_visa_alias_success() -> None:
    req, handlers = visa_alias_case(VISA_ALIAS_SUCCESS)
    with client(handlers) as c:
        response = c.verify_visa_alias(req)
    assert isinstance(response, models.VisaAliasPhoneResponse)
    assert isinstance(response, models.CreditCardInfo)
    assert response.token == "visa-alias-token"
    assert response.service_info is not None
    assert response.service_info.recipient_name == "Test Recipient"
    assert response.model_dump(by_alias=True, exclude_none=True) == VISA_ALIAS_SUCCESS


@pytest.mark.parametrize("status,payload", VISA_ALIAS_ERRORS)
def test_visa_alias_http_error(status: int, payload: dict) -> None:
    req, handlers = visa_alias_case(payload, status)
    with client(handlers) as c, pytest.raises(ApiError) as exc:
        c.verify_visa_alias(req)
    assert exc.value.status == status
    assert exc.value.message == payload["message"]
    assert exc.value.errors == payload.get("errors")
    assert exc.value.error_code == payload.get("error_code")
    assert exc.value.code == payload["code"]
    assert exc.value.friendly_message == payload["friendly_message"]
    assert str(exc.value) == f"API error {status}: {payload['message']}"


def test_visa_alias_requires_phone_string() -> None:
    for body in ({}, {"recipient_info": {}}, {"recipient_info": {"phone_number": 123}}):
        with pytest.raises(ValidationError):
            models.VisaAliasPhoneRequest.model_validate(body)


def p2p_case(operation: str) -> tuple:
    body = {
        "amount": 100,
        "currency": "EUR",
        "credit_card": {"token": "sender-token"},
        "recipient_card": {"token": "recipient-token"},
        "test": False,
        "tracking_id": "p2p-1",
        "expired_at": "2026-09-18T10:00:00Z",
        "duplicate_check": False,
        "language": "en",
        "notification_url": "https://example.com/notify",
        "return_url": "https://example.com/return",
        "customer": {"email": "customer@example.com", "ip": "127.0.0.1"},
        "sender_billing_address": {"first_name": "Sender", "country": "BY"},
        "recipient_billing_address": {"first_name": "Recipient", "country": "BY"},
        "billing_address": {"city": "Minsk", "zip": "220000"},
        "additional_data": {
            "p2p": {"type": "a2a"},
            "referer": "https://example.com",
            "receipt_text": ["Transfer receipt"],
            "contract": ["recurring"],
        },
    }
    if operation == "create_p2p":
        body["description"] = "Transfer"
        payload = {
            "uid": "p2p-1",
            "id": "123",
            "status": "successful",
            "status_code": 0,
            "type": "p2p",
            "amount": 100,
            "currency": "EUR",
            "description": "Transfer",
            "tracking_id": "p2p-1",
            "test": False,
            "message": "Successfully processed",
            "created_at": "2026-09-17T10:00:00Z",
            "updated_at": "2026-09-17T10:00:01Z",
            "paid_at": "2026-09-17T10:00:01Z",
            "language": "en",
            "payment_method_type": "credit_card",
            "additional_data": {"unknown": {"values": [False, None, 0]}},
            "customer": body["customer"],
            "billing_address": body["billing_address"],
            "sender_billing_address": body["sender_billing_address"],
            "recipient_billing_address": body["recipient_billing_address"],
            "credit_card": {"brand": "visa", "token": "sender-token"},
            "recipient_card": {"brand": "visa", "token": "recipient-token"},
            "p2p": {"status": "successful"},
            "verify_p2p": {"status": "successful"},
            "receipt_url": "https://example.com/receipt",
            "redirect_url": "https://example.com/return",
        }
        path = "/transactions/p2ps"
        version = "3"
        response = {"transaction": payload}
    else:
        payload = {
            "status": "error",
            "message": "Invalid request",
            "test": False,
            "error_code": "request_validation_error",
            "errors": {"recipient_card": {"number": ["is invalid"]}},
            "required_fields": {"credit_card": ["number"], "recipient_card": []},
        }
        path = "/p2p-restrictions"
        version = None
        response = payload
    handlers = {
        ("POST", path): {
            "expect_host": "gateway.bepaid.by",
            "expect_version": version,
            "expect_body": {"request": body},
            "json": response,
        }
    }
    return P2pRequest.model_validate(body), payload, handlers


@pytest.mark.parametrize("operation", ["create_p2p", "verify_p2p"])
def test_p2p_preserves_full_payload(operation: str) -> None:
    req, payload, handlers = p2p_case(operation)
    with client(handlers) as c:
        response = getattr(c, operation)(req)
    assert response.model_dump(exclude_none=True) == payload


def test_p2p() -> None:
    c = client(
        {
            ("POST", "/transactions/p2ps"): {
                "expect_version": "3",
                "json": {
                    "transaction": {
                        "uid": "1-82cc07d15d",
                        "status": "successful",
                        "type": "p2p",
                        "amount": 100,
                        "currency": "EUR",
                        "credit_card": {"brand": "visa", "last_4": "1112"},
                        "recipient_card": {"brand": "visa", "last_4": "0000"},
                    }
                },
            }
        }
    )
    resp = c.create_p2p(
        P2pRequest(
            amount=100,
            currency="EUR",
            credit_card={
                "number": "4012001037141112",
                "holder": "John Doe",
                "verification_value": "123",
                "exp_month": "12",
                "exp_year": "2028",
            },
            recipient_card={"number": "4200000000000000"},
            test=True,
        )
    )
    assert resp.status == "successful"
    assert resp.type == "p2p"
    assert resp.credit_card is not None
    assert resp.credit_card.brand == "visa"


def test_verify_p2p() -> None:
    c = client(
        {
            ("POST", "/p2p-restrictions"): {
                "json": {
                    "status": "successful",
                    "message": "p2p is allowed",
                    "commission": {
                        "minimum": 0.7,
                        "percent": 1.5,
                        "bank_fee": 7.35,
                        "currency": "USD",
                    },
                }
            }
        }
    )
    resp = c.verify_p2p(
        P2pRequest(
            amount=100,
            currency="USD",
            credit_card={"number": "4012001037141112"},
            recipient_card={"number": "4200000000000000"},
            test=True,
        )
    )
    assert resp.status == "successful"
    assert resp.commission is not None
    assert resp.commission.currency == "USD"
    assert resp.commission.percent == 1.5


def test_customer_create_get_list() -> None:
    c = client(
        {
            ("POST", "/customers"): {
                "json": {
                    "id": "cst_7aee5afb954c7ef7",
                    "first_name": "John",
                    "last_name": "Doe",
                    "email": "customer@example.com",
                }
            },
            ("GET", "/customers/cst_7aee5afb954c7ef7"): {
                "json": {"id": "cst_7aee5afb954c7ef7", "email": "customer@example.com"}
            },
            ("GET", "/customers"): {
                "json": [
                    {"id": "cst_7aee5afb954c7ef7", "email": "customer@example.com"}
                ]
            },
        }
    )
    created = c.create_customer(
        CustomerRecord(
            first_name="John",
            last_name="Doe",
            email="customer@example.com",
            ip="127.0.0.1",
        )
    )
    assert created.id == "cst_7aee5afb954c7ef7"
    fetched = c.get_customer("cst_7aee5afb954c7ef7")
    assert fetched.email == "customer@example.com"
    listed = c.list_customers()
    assert len(listed) == 1
    assert listed[0].email == "customer@example.com"


def test_plan_create_list() -> None:
    c = client(
        {
            ("POST", "/plans"): {
                "json": {
                    "id": "pln_2b0c211f50deb72c",
                    "title": "Basic plan",
                    "currency": "USD",
                    "plan": {"amount": 20, "interval": 7, "interval_unit": "day"},
                    "number_payment_attempts": 3,
                    "test": True,
                }
            },
            ("GET", "/plans"): {
                "json": [{"id": "pln_2b0c211f50deb72c", "title": "Basic plan"}]
            },
        }
    )
    p = c.create_plan(
        PlanItem(
            test=True,
            title="Basic plan",
            currency="USD",
            plan={"amount": 20, "interval": 7, "interval_unit": "day"},
            number_payment_attempts=3,
        )
    )
    assert p.id == "pln_2b0c211f50deb72c"
    plans = c.list_plans()
    assert len(plans) == 1
    assert plans[0].title == "Basic plan"


def test_subscription_create_and_cancel() -> None:
    c = client(
        {
            ("POST", "/subscriptions"): {
                "json": {
                    "id": "sbs_cce60e7f2d661bc0",
                    "state": "active",
                    "tracking_id": "my_tracking_id",
                    "card": {"brand": "master", "last_4": "5003", "token": "tok_1"},
                    "customer": {"id": "cst_ec240ca02bac424b"},
                    "plan": {"id": "pln_f5ee5ebd04e39daa", "title": "Basic plan"},
                }
            },
            ("POST", "/subscriptions/sbs_cce60e7f2d661bc0/cancel"): {
                "json": {"state": "canceled"}
            },
        }
    )
    s = c.create_subscription(
        SubscriptionCreateRequest(
            card={"token": "tok_1"},
            customer={"id": "cst_ec240ca02bac424b"},
            plan={"id": "pln_f5ee5ebd04e39daa"},
            tracking_id="my_tracking_id",
        )
    )
    assert s.state == "active"
    assert s.card is not None
    assert s.card.brand == "master"
    r = c.cancel_subscription(
        "sbs_cce60e7f2d661bc0",
        CancelSubscriptionRequest(cancel_reason="Customer's request"),
    )
    assert r["state"] == "canceled"


def test_create_payout_happy_path() -> None:
    c = client(
        {
            ("POST", "/transactions/payouts"): {
                "expect_version": "3",
                "json": {
                    "transaction": {
                        "uid": "1-310b0da80b",
                        "type": "payout",
                        "status": "successful",
                        "amount": 100,
                        "currency": "USD",
                        "test": True,
                        "tracking_id": "payout-1",
                        "payout": {"status": "successful", "rrn": "1234"},
                        "customer": {
                            "ip": "127.0.0.1",
                            "email": "john@example.com",
                        },
                    }
                },
            }
        }
    )
    p = c.create_payout(
        PayoutRequest(
            test=True,
            amount=100,
            currency="USD",
            description="Payout",
            tracking_id="payout-1",
            recipient=PayoutCustomer(
                ip="127.0.0.1", email="john@example.com", birth_date="1990-10-20"
            ),
            sender=PayoutCustomer(
                ip="127.0.0.1", email="john@example.com", birth_date="1990-10-20"
            ),
            recipient_billing_address=PayoutAddress(
                country="US",
                city="Denver",
                state="CO",
                zip="96002",
                address="1st Street",
            ),
            sender_billing_address=PayoutAddress(
                country="US",
                city="Denver",
                state="CO",
                zip="96002",
                address="1st Street",
            ),
        )
    )
    assert p.status == "successful"
    assert p.type == "payout"
    assert p.payout is not None
    assert p.payout.rrn == "1234"


def test_get_balance_happy_path() -> None:
    c = client(
        {
            ("POST", "/beyag/balance"): {
                "json": {
                    "status": "Successful",
                    "code": "S.0000",
                    "gateway_id": 1234,
                    "account": "40701810842020395221",
                    "amount": 1290092162,
                    "currency": "USD",
                }
            }
        }
    )
    b = c.get_balance(
        BalanceRequest(
            gateway_id=1234,
            account="40701810842020395221",
            currency="USD",
        )
    )
    assert b.status == "Successful"
    assert b.amount == 1290092162


def test_currency_query_happy_path() -> None:
    c = client(
        {
            ("POST", "/beyag/currencies"): {
                "json": {
                    "status": "Successful",
                    "code": "S.0000",
                    "friendly_message": "Successfully processed",
                    "gateway_id": 1234,
                    "account": "40701810842020395221",
                    "country": "GB",
                    "currency": "TRX",
                    "provider_info": {
                        "currency": "TRX",
                        "alias": "Tron",
                        "allowDeposit": True,
                        "allowWithdrawal": True,
                        "priceUSD": "0.05963000",
                        "networks": [{"name": "tron"}],
                    },
                }
            }
        }
    )
    info = c.get_currencies(
        CurrencyQueryRequest(
            gateway_id=1234,
            account="40701810842020395221",
            country="GB",
        )
    )
    assert info.status == "Successful"
    assert info.currency == "TRX"
    assert info.provider_info is not None
    assert info.provider_info["networks"][0]["name"] == "tron"


def test_get_reports_happy_path() -> None:
    c = client(
        {
            ("POST", "/api/reports"): {
                "expect_version": "2",
                "json": {
                    "transactions": [
                        {
                            "uid": "20527-b7ea8c95f4",
                            "id": 28859,
                            "type": "authorization",
                            "status": "failed",
                            "amount": 1000,
                            "currency": "USD",
                            "credit_card": {"brand": "visa", "last_4": "1006"},
                        }
                    ],
                    "count": 1,
                },
            }
        }
    )
    r = c.get_reports(
        ReportListRequest(
            report_params=ReportParams(
                date_type="created_at",
                date="2022-01-27",
                status="failed",
                payment_method_type="credit_card",
                time_zone="Europe/London",
            )
        )
    )
    assert r.count == 1
    assert r.transactions[0].uid == "20527-b7ea8c95f4"


def test_get_report_count_happy_path() -> None:
    c = client(
        {
            ("POST", "/api/reports/count"): {
                "expect_version": "3",
                "json": {"transactions": {"count": 2}},
            }
        }
    )
    r = c.get_report_count(
        ReportCountRequest(
            report_params=ReportCountParams(
                date_type="created_at",
                from_="2022-01-25 00:00:00",
                to="2022-01-27 23:59:59",
                status="incomplete",
                payment_method_type="credit_card",
                time_zone="Etc/UTC",
            )
        )
    )
    assert r.transactions.count == 2


def test_get_channel_balances_happy_path() -> None:
    c = client(
        {
            ("GET", "/shop/channel_balances/"): {
                "json": [{"gateway_id": 3405, "currency": "USD", "amount": 100}]
            }
        }
    )
    bals = c.get_channel_balances(3405, "USD")
    assert len(bals) == 1
    assert bals[0].gateway_id == 3405
    assert bals[0].amount == 100


def test_create_split_payment_happy_path() -> None:
    c = client(
        {
            ("POST", "/splits/payment"): {
                "json": {
                    "splits": [
                        {
                            "uid": "21-99834feb0b",
                            "amount": 70,
                            "status": "successful",
                            "shop_id": 91,
                            "parent": True,
                        },
                        {
                            "uid": "22-56784ffecd",
                            "amount": 30,
                            "status": "successful",
                            "shop_id": 1111,
                            "parent": False,
                            "parent_uid": "21-99834feb0b",
                        },
                    ]
                }
            }
        }
    )
    r = c.create_split_payment(
        SplitPaymentRequest(
            amount=100,
            currency="USD",
            description="Split payment",
            tracking_id="split-1",
            credit_card=SplitCreditCard(token="token_123"),
            additional_data=SplitAdditionalData(split={"241": 40, "242": 50}),
        )
    )
    assert len(r.splits) == 2
    assert r.splits[0].parent is True
    assert r.splits[1].parent_uid == "21-99834feb0b"


_PRODUCT = {
    "id": "prd_ed27b047d3ccd1a6",
    "name": "product",
    "description": "description of product",
    "currency": "USD",
    "amount": 990,
    "quantity": 10,
    "infinite": False,
    "language": "en",
    "transaction_type": "payment",
    "created_at": "2022-12-20T18:54:42.033Z",
    "updated_at": "2022-12-20T18:54:42.033Z",
    "test": False,
    "additional_data": {},
    "pay_url": "https://api.bepaid.by/products/prd_ed27b047d3ccd1a6/pay",
    "payment_url": "https://api.bepaid.by/products/prd_ed27b047d3ccd1a6/pay",
    "confirm_url": "https://checkout.bepaid.by/v2/confirm_order/prd_ed27b047d3ccd1a6/1",
}


def test_create_product_happy_path() -> None:
    c = client({("POST", "/products"): {"json": _PRODUCT}})
    r = c.create_product(
        ProductCreateRequest(
            name="product",
            description="description of product",
            currency="USD",
            amount=990,
            quantity="10",
            language="en",
            transaction_type="payment",
        )
    )
    assert r.id == "prd_ed27b047d3ccd1a6"
    assert r.amount == 990
    assert r.pay_url == "https://api.bepaid.by/products/prd_ed27b047d3ccd1a6/pay"


def test_list_products_happy_path() -> None:
    c = client({("GET", "/products"): {"json": [_PRODUCT]}})
    r = c.list_products()
    assert len(r) == 1
    assert r[0].id == "prd_ed27b047d3ccd1a6"


def test_get_product_happy_path() -> None:
    c = client({("GET", "/products/prd_ed27b047d3ccd1a6"): {"json": _PRODUCT}})
    r = c.get_product("prd_ed27b047d3ccd1a6")
    assert r.id == "prd_ed27b047d3ccd1a6"


def test_update_product_happy_path() -> None:
    c = client({("PUT", "/products/prd_1"): {"status": 204}})
    c.update_product(
        "prd_1",
        ProductUpdateRequest(amount=950, infinite=False, quantity="5"),
    )


def test_get_apm_transaction() -> None:
    c = client(
        {
            ("GET", "/beyag/transactions/apm1"): {
                "json": {
                    "transaction": {
                        "uid": "apm1",
                        "type": "payment",
                        "status": "successful",
                        "amount": 100,
                        "currency": "BYN",
                    }
                }
            }
        }
    )
    t = c.get_apm_transaction("apm1")
    assert t.status == "successful"
    assert t.amount == 100


def test_get_apm_transactions_by_tracking_id() -> None:
    c = client(
        {
            ("GET", "/beyag/transactions/tracking_id/tracking_1"): {
                "json": {
                    "transactions": [
                        {"uid": "apm1", "type": "payment", "status": "successful"},
                        {"uid": "apm2", "type": "payment", "status": "failed"},
                    ]
                }
            }
        }
    )
    ts = c.get_apm_transactions_by_tracking_id("tracking_1")
    assert [t.uid for t in ts] == ["apm1", "apm2"]


def test_apm_payout() -> None:
    c = client(
        {
            ("POST", "/beyag/transactions/payouts"): {
                "json": {
                    "transaction": {
                        "uid": "pay1",
                        "type": "payout",
                        "status": "successful",
                        "amount": 100,
                        "currency": "USD",
                        "payout": {"status": "successful", "gateway_id": 85},
                    }
                }
            }
        }
    )
    p = c.apm_payout(
        ApmPayoutRequest(
            amount=100,
            currency="USD",
            description="payout",
            method={"type": "ad_payments"},
        )
    )
    assert p.status == "successful"
    assert p.payout is not None
    assert p.payout["gateway_id"] == 85


def test_apm_proof() -> None:
    c = client(
        {
            ("POST", "/beyag/transactions/apm1/proof"): {
                "json": {
                    "transaction": {
                        "uid": "pr1",
                        "parent_uid": "apm1",
                        "type": "proof",
                        "status": "successful",
                        "amount": 71267,
                        "currency": "USD",
                        "proof": {"message": "Proof was successfully processed."},
                    }
                }
            }
        }
    )
    r = c.apm_proof(
        "apm1",
        ProofRequest(
            amount=71267,
            currency="USD",
            document=ProofDocument(
                content_type="application/pdf",
                file_name="proof.pdf",
                file_size=12345,
                content="base64...",
                checksum="sha256...",
            ),
        ),
    )
    assert r.status == "successful"
    assert r.parent_uid == "apm1"
    assert r.proof is not None
    assert r.proof["message"] == "Proof was successfully processed."


def test_check_mts_service() -> None:
    c = client(
        {
            ("POST", "/beyag/gateways/mts_money_widget/check_service"): {
                "expect_version": "3",
                "json": {
                    "service_activated": True,
                    "message": None,
                    "validation": {"operator": "mts", "message": "OK"},
                },
            }
        }
    )
    r = c.check_mts_service("375295222222", test=True)
    assert r.service_activated is True
    assert r.validation is not None
    assert r.validation.operator == "mts"


def test_erip_payments() -> None:
    handlers = {
        ("GET", "/beyag/payments/ep1"): {
            "json": {
                "transaction": {
                    "uid": "ep1",
                    "status": "pending",
                    "amount": 1000,
                    "currency": "BYN",
                    "payment_method_type": "erip",
                    "order_id": "633602201673",
                    "erip": {"account_number": "123"},
                }
            }
        },
        ("GET", "/beyag/payments/"): {
            "json": {
                "transaction": {
                    "uid": "ep2",
                    "status": "pending",
                    "order_id": "633602201673",
                }
            }
        },
        ("DELETE", "/beyag/payments/ep1"): {
            "json": {
                "transaction": {
                    "uid": "ep1",
                    "status": "deleted",
                    "order_id": "633602201673",
                }
            }
        },
    }
    c = client(handlers)
    t = c.get_erip_payment("ep1")
    assert t.uid == "ep1"
    assert t.status == "pending"
    assert t.erip is not None
    t = c.get_erip_payment_by_order_id("633602201673")
    assert t.uid == "ep2"
    t = c.delete_erip_payment("ep1")
    assert t.status == "deleted"


INTEGRATION_CASES = [
    "checkout",
    "checkout_status",
    "balance",
    "payment",
    "authorization",
    "payment_async",
    "authorization_async",
    "confirm_reference",
    "confirm_skip",
    "confirm_empty",
    "apm_payment",
    "apm_refund",
    "product",
    "payout",
]


def integration_case(case: str) -> tuple:
    method = "POST"
    host = "gateway.bepaid.by"
    version = "3"
    request_id = None
    response_type = models.Transaction
    payload = {"uid": "integration-1", "status": "successful"}
    response = {"transaction": payload}
    if case in ("payment", "authorization", "payment_async", "authorization_async"):
        operation = f"create_{case}"
        kind = case.removesuffix("_async")
        body = {
            "amount": "100" if kind == "payment" else 100,
            "currency": "BYN",
            "test": False,
            "description": "Integration",
            "tracking_id": "integration-1",
            "language": "en",
            "notification_url": "https://example.com/notify",
            "return_url": "https://example.com/return",
            "expired_at": "2026-09-18T10:00:00Z",
            "dynamic_billing_descriptor": "SHOP",
            "additional_data": {"p2p": {"service_id": "x", "service_extension": "y"}},
        }
        request_type = PaymentRequest if kind == "payment" else AuthorizationRequest
        request_id = "integration-request"
        args = (request_type.model_validate(body), request_id)
        path = f"/transactions/{kind}s"
        payload = {
            **payload,
            "tracking_id": "integration-1",
            "message": "Approved",
            "credit_card": {"token": "saved-token"},
            "code": "S.0000",
            "redirect_url": "https://example.com/return",
            "payment": {},
            "three_d_secure_verification": {"status": "successful", "eci": "05"},
        }
        response = {"transaction": payload}
        if case.endswith("_async"):
            path = "/async" + path
            response_type = models.AsyncAck
            payload = {
                "status": "pending",
                "request_id": request_id,
                "status_url": "https://gateway.bepaid.by/async/status/integration-1",
                "response_url": "https://gateway.bepaid.by/async/response/integration-1",
            }
            response = payload
        body = {"request": body}
    elif case in ("checkout", "checkout_status"):
        host, version = "checkout.bepaid.by", "2"
        settings = {
            "style": {"button": {"color": "red"}},
            "widget_version": "2",
            "require": {"email": True},
            "customer": {"read_only": ["email"]},
        }
        body = {
            "transaction_type": "payment",
            "order": {"amount": 100, "currency": "BYN"},
            "settings": settings,
            "dynamic_billing_descriptor": "SHOP",
            "travel": {"airline": {"ticket_number": "123"}},
        }
        payload = {
            **body,
            "token": "integration-1",
            "customer": {"email": "test@example.com"},
            "payment_method": {"types": ["credit_card"]},
        }
        operation, path = "create_checkout", "/ctp/api/checkouts"
        args = (CheckoutRequest.model_validate(body),)
        body = {"checkout": body}
        response_type = models.CheckoutResponse
        if case == "checkout_status":
            method, version = "GET", None
            operation, path = "get_checkout_status", path + "/integration-1"
            args = ("integration-1",)
            response_type = models.CheckoutStatus
            payload.update(
                merchant={"name": "Shop"},
                version="2",
                card_info={"brand": "visa"},
                job_id="job-1",
                attempts=0,
                iframe=False,
            )
        response = {"checkout": payload}
    elif case == "balance":
        operation, path, version = "get_card_balance", "/balance", "2"
        body = {"account": "account-1", "currency": "BYN", "gateway_id": 42}
        args = (models.CardBalanceRequest.model_validate(body),)
        body = {"request": body}
        payload = {
            "status": "successful",
            "result": {
                "gatewayId": 42,
                "account": "account-1",
                "amount": 0,
                "currency": "BYN",
                "bankInfo": {"name": "Bank"},
            },
        }
        response, response_type = payload, models.CardBalanceResponse
    elif case.startswith("confirm_"):
        host, version = "api.bepaid.by", None
        operation, path = (
            "confirm_apm_payment",
            "/beyag/transactions/integration-1/confirm",
        )
        fields: dict[str, bool | str] = (
            {} if case == "confirm_empty" else {"skip_duplicate_check": False}
        )
        if case == "confirm_reference":
            fields["transaction_reference"] = "receipt-1"
        args = ("integration-1", ApmConfirmRequest.model_validate(fields))
        body = {"request": fields}
        payload = {"parent_uid": "integration-1", "status": "successful"}
        response, response_type = {"response": payload}, models.ApmConfirmResponse
    elif case == "apm_payment":
        host, version = "api.bepaid.by", None
        operation, path = "create_apm_payment", "/beyag/transactions/payments"
        body = {
            "amount": 100,
            "currency": "BYN",
            "payment_method": {"type": "pix"},
            "iframe": False,
            "verification_url": "https://example.com/verify",
            "customer": {"id": "customer-1", "id_number": "123"},
        }
        args = (ApmPaymentRequest.model_validate(body),)
        body["method"] = body.pop("payment_method")
        body = {"request": body}
        response_type = models.ApmPaymentResponse
    elif case == "apm_refund":
        host, version = "api.bepaid.by", None
        operation, path = "apm_refund", "/beyag/transactions/refunds"
        args = (ApmRefundRequest(parent_uid="integration-1", reason="Requested"),)
        body = {"request": {"parent_uid": "integration-1", "reason": "Requested"}}
        payload = {
            **payload,
            "tracking_id": "refund-1",
            "updated_at": "2026-09-17T10:00:00Z",
            "method_type": "pix",
            "receipt_url": "https://example.com/receipt",
            "smart_routing_verification": {"status": "successful"},
            "additional_data": {"receipt_text": ["Refund"]},
        }
        response, response_type = {"transaction": payload}, models.ApmRefundResponse
    elif case == "product":
        method, host, version = "PUT", "api.bepaid.by", None
        operation, path = "update_product", "/products/integration-1"
        body = {
            "name": "Updated",
            "description": "Product",
            "currency": "BYN",
            "visible_fields": ["email"],
            "test": False,
            "immortal": False,
            "expired_at": "2026-09-18T10:00:00Z",
            "return_url": "https://example.com/return",
            "shop_id": "363",
            "language": "en",
            "transaction_type": "payment",
            "amount": 100,
            "infinite": False,
            "quantity": "1",
        }
        args = ("integration-1", ProductUpdateRequest.model_validate(body))
        payload = response = None
        response_type = type(None)
    else:
        operation, path = "create_payout", "/transactions/payouts"
        body = {
            "amount": 100,
            "currency": "BYN",
            "recipient": {},
            "sender": {},
            "recipient_billing_address": {},
            "sender_billing_address": {},
            "additional_data": {
                "p2p": {"service_id": "x", "service_extension": "y"},
                "sub_brand": "brand",
                "receipt_text": ["Receipt"],
                "card_on_file": True,
                "expected_bank_code": "bank",
                "excluded_gateways": [42],
            },
        }
        args = (PayoutRequest.model_validate(body),)
        body = {"request": body}
        response_type = models.PayoutResponse
    spec = {
        "expect_host": host,
        "expect_version": version,
        "expect_request_id": request_id,
        "json": response,
    }
    if method != "GET":
        spec["expect_body"] = body
    return operation, args, payload, response_type, {(method, path): spec}


@pytest.mark.parametrize("case", INTEGRATION_CASES)
def test_integration_contract(case: str) -> None:
    operation, args, payload, response_type, handlers = integration_case(case)
    with client(handlers) as c:
        result = getattr(c, operation)(*args)
    assert isinstance(result, response_type)
    assert (
        result.model_dump(by_alias=True, exclude_unset=True) if result else None
    ) == payload


def async_processing_flow() -> dict:
    return {
        ("GET", "/async/status/integration-1"): {
            "expect_host": "gateway.bepaid.by",
            "json": {
                "status": "completed",
                "request_id": "integration-request",
                "response_url": "https://gateway.bepaid.by/async/response/integration-1",
            },
        },
        ("GET", "/async/response/integration-1"): {
            "expect_host": "gateway.bepaid.by",
            "json": {
                "transaction": {
                    "uid": "integration-1",
                    "status": "successful",
                    "credit_card": {"token": "saved-token"},
                }
            },
        },
    }


def test_async_processing_completed_flow() -> None:
    with client(async_processing_flow()) as c:
        status = c.get_async_status(
            "https://gateway.bepaid.by/async/status/integration-1"
        )
        assert isinstance(status, models.AsyncStatus)
        assert status.status == "completed"
        assert status.request_id == "integration-request"
        assert status.response_url is not None
        result = c.get_async_result(status.response_url)
    assert isinstance(result, models.Transaction)
    assert result.uid == "integration-1"
    assert result.credit_card is not None and result.credit_card.token == "saved-token"


POLLING_INVALID_URLS = [
    "https://other.test/async/status/1",
    "http://gateway.test/async/status/1",
    "https://gateway.test:8443/async/status/1",
    "https://user:password@gateway.test/async/status/1",
    "https://@gateway.test/async/status/1",
    "/async/status/1",
    "//gateway.test/async/status/1",
    "https:///async/status/1",
    "https://gateway.test:invalid/async/status/1",
    "https://[invalid/async/status/1",
    "https://gateway.test/async/status/1#fragment",
    "https://gateway.test/async/status/with space",
    "https://gateway.test/async/status/1\n",
    "https://gateway.test/async\\status/1",
]


@pytest.mark.parametrize("operation", ["get_async_status", "get_async_result"])
@pytest.mark.parametrize("url", POLLING_INVALID_URLS)
def test_polling_rejects_invalid_url(operation: str, url: str) -> None:
    with (
        BepaidClient(
            SHOP_ID,
            SECRET,
            base_gateway_url="https://gateway.test",
            transport=MockTransport({}),
        ) as c,
        pytest.raises(ValueError, match="configured gateway origin"),
    ):
        getattr(c, operation)(url)


@pytest.mark.parametrize("operation", ["get_async_status", "get_async_result"])
@pytest.mark.parametrize(
    "gateway,url",
    [
        ("https://gateway.test", "https://GATEWAY.test:443/async/status/1?job=1"),
        ("https://gateway.test:8443/base", "https://gateway.test:8443/async/status/1"),
        ("http://localhost:8080", "http://localhost:8080/async/status/1"),
    ],
)
def test_polling_accepts_configured_origin(
    operation: str, gateway: str, url: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == AUTH
        assert request.url == httpx.URL(url)
        return httpx.Response(
            200, json={"status": "completed", "transaction": {"uid": "poll-1"}}
        )

    with BepaidClient(
        SHOP_ID,
        SECRET,
        base_gateway_url=gateway,
        transport=httpx.MockTransport(handler),
    ) as c:
        result = getattr(c, operation)(url)
    assert (
        result.status == "completed"
        if operation == "get_async_status"
        else result.uid == "poll-1"
    )


@pytest.mark.parametrize("operation", ["get_async_status", "get_async_result"])
@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("location", ["/next", "https://other.test/next"])
def test_polling_rejects_redirects(operation: str, status: int, location: str) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert len(requests) == 1
        assert request.url == httpx.URL("https://gateway.test/async/status/1")
        return httpx.Response(status, headers={"Location": location})

    with BepaidClient(
        SHOP_ID,
        SECRET,
        base_gateway_url="https://gateway.test",
        transport=httpx.MockTransport(handler),
    ) as c:
        c._client().http.follow_redirects = True
        with pytest.raises(ApiError, match="polling redirects") as exc:
            getattr(c, operation)("https://gateway.test/async/status/1")
        assert exc.value.status == status
    assert len(requests) == 1


def test_non_polling_keeps_client_redirect_setting() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(302, headers={"Location": "/next"})
        return httpx.Response(200, json={"transaction": {"uid": "poll-1"}})

    with BepaidClient(
        SHOP_ID,
        SECRET,
        base_gateway_url="https://gateway.test",
        transport=httpx.MockTransport(handler),
    ) as c:
        c._client().http.follow_redirects = True
        assert c.get_transaction("poll-1").uid == "poll-1"
    assert len(requests) == 2


def test_integration_webhook_birth_date() -> None:
    payload = {
        "transaction": {
            "uid": "integration-1",
            "status": "successful",
            "billing_address": {"birth_date": "1990-10-20"},
        }
    }
    assert parse_webhook(json.dumps(payload)).model_dump(exclude_unset=True) == payload


@pytest.mark.parametrize("version", [2, "2"])
def test_checkout_status_version(version: int | str) -> None:
    status = models.CheckoutStatus.model_validate({"version": version})
    assert status.model_dump(exclude_unset=True) == {"version": version}


def test_integration_optional_fields_omitted() -> None:
    assert models.ProductUpdateRequest().model_dump(exclude_none=True) == {}
    assert models.CheckoutSettings().model_dump(exclude_none=True) == {}
    assert models.Customer().model_dump(exclude_none=True) == {}
    assert models.CardBalanceRequest().model_dump(exclude_none=True) == {}


def test_checkup() -> None:
    c = client(
        {
            ("POST", "/transactions/checkups"): {
                "expect_version": "3",
                "json": {
                    "transaction": {
                        "uid": "c1",
                        "type": "payment",
                        "status": "successful",
                        "amount": 100,
                        "currency": "USD",
                        "payment_method_type": "credit_card",
                    }
                },
            }
        }
    )
    t = c.checkup(
        CheckupRequest(
            amount=100,
            currency="USD",
            description="checkup",
            tracking_id="tracking_1",
            credit_card=ChargeCreditCard(token="tok1"),
        )
    )
    assert t.status == "successful"
    assert t.amount == 100
