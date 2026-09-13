"""Tests for the bepaid client using a mocked httpx transport."""

from __future__ import annotations

import json

import httpx
import pytest

from bepaid import AsyncBepaidClient, BepaidClient, BepaidError
from bepaid.client import verify_webhook_auth
from bepaid.errors import ApiError
from bepaid.models import (
    ApmPaymentRequest,
    ApmRefundRequest,
    AuthorizationRequest,
    CaptureRequest,
    CheckoutOrder,
    CheckoutRequest,
    CreateTokenRequest,
    PaymentRequest,
    RefundRequest,
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
        if "expect_body" in spec:
            assert json.loads(request.content) == spec["expect_body"]
        return httpx.Response(
            spec.get("status", 200),
            json=spec["json"],
            request=request,
        )


def client(handlers: dict) -> BepaidClient:
    return BepaidClient(SHOP_ID, SECRET, transport=MockTransport(handlers))


def async_client(handlers: dict) -> AsyncBepaidClient:
    return AsyncBepaidClient(SHOP_ID, SECRET, transport=MockTransport(handlers))


def _payment_request() -> PaymentRequest:
    return PaymentRequest(
        amount="700",
        currency="USD",
        test=True,
        description="Test transaction",
        tracking_id="tracking_id_000",
    )


def test_create_payment_happy_path() -> None:
    c = client(
        {
            ("POST", "/transactions/payments"): {
                "json": {"transaction": {"tracking_id": "tracking_id_000", "uid": "u1"}}
            }
        }
    )
    resp = c.create_payment(_payment_request())
    assert resp.uid == "u1"


def test_create_payment_serializes_request() -> None:
    c = client(
        {
            ("POST", "/transactions/payments"): {
                "json": {"transaction": {"uid": "u1"}},
                "expect_body": {
                    "request": {
                        "amount": "700",
                        "currency": "USD",
                        "test": True,
                        "description": "Test transaction",
                        "trackingId": "tracking_id_000",
                    }
                },
            }
        }
    )
    c.create_payment(_payment_request())


def test_api_error_raises() -> None:
    c = client(
        {
            ("POST", "/transactions/payments"): {
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


def test_create_authorization_returns_redirect() -> None:
    c = client(
        {
            ("POST", "/transactions/authorizations"): {
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
                }
            }
        }
    )
    resp = c.create_authorization(
        AuthorizationRequest(
            amount=100, currency="USD", description="Test", tracking_id="x"
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
                "json": {
                    "transaction": {
                        "uid": "c1",
                        "status": "successful",
                        "type": "capture",
                        "parent_uid": "p1",
                    }
                }
            },
            ("POST", "/transactions/voids"): {
                "json": {
                    "transaction": {
                        "uid": "v1",
                        "status": "successful",
                        "type": "void",
                    }
                }
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
                "json": {
                    "transaction": {
                        "uid": "r1",
                        "parent_uid": "p1",
                        "type": "refund",
                        "status": "successful",
                    }
                }
            }
        }
    )
    resp = c.refund(RefundRequest(parent_uid="p1", amount=50, reason="Client request"))
    assert resp.status == "successful"
    assert resp.type == "refund"


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


def test_create_token() -> None:
    c = client(
        {
            ("POST", "/credit_cards"): {
                "json": {
                    "holder": "John Doe",
                    "brand": "visa",
                    "last_4": "0000",
                    "token": "7ba647e7013b5cb9df39f17c375783aef",
                    "exp_month": 1,
                    "exp_year": 2028,
                }
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


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (AUTH, True),
        ("Basic bm90OnJpZ2h0", False),
    ],
)
def test_verify_webhook_auth(header: str, expected: bool) -> None:
    assert verify_webhook_auth(header, SHOP_ID, SECRET) is expected


def test_errors_baseclass() -> None:
    assert issubclass(ApiError, BepaidError)
