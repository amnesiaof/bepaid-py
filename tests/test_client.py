"""Tests for the bepaid client using a mocked httpx transport."""

from __future__ import annotations

import json

import httpx
import pytest

from bepaid import AsyncBepaidClient, BepaidClient, BepaidError
from bepaid.client import verify_webhook_auth
from bepaid.errors import ApiError
from bepaid.models import (
    ApmConfirmRequest,
    ApmPaymentRequest,
    ApmRefundRequest,
    AuthorizationRequest,
    CancelSubscriptionRequest,
    CaptureRequest,
    CheckoutOrder,
    CheckoutRequest,
    CreateTokenRequest,
    CustomerRecord,
    P2pRequest,
    PaymentRequest,
    PlanItem,
    RefundRequest,
    SubscriptionCreateRequest,
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


def test_p2p() -> None:
    c = client(
        {
            ("POST", "/transactions/p2ps"): {
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
                }
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
