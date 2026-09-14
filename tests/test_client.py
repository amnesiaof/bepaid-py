"""Tests for the bepaid client using a mocked httpx transport."""

from __future__ import annotations

import json

import httpx
import pytest

from bepaid import AsyncBepaidClient, BepaidClient, BepaidError
from bepaid.client import verify_webhook_auth, verify_webhook_signature
from bepaid.errors import ApiError
from bepaid.models import (
    ApmConfirmRequest,
    ApmPaymentRequest,
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
    CreateTokenRequest,
    CurrencyQueryRequest,
    CustomerRecord,
    Fiscalization,
    FiscalizationPosition,
    FiscalizationTax,
    P2pRequest,
    PaymentRequest,
    PayoutAddress,
    PayoutCreditCard,
    PayoutCustomer,
    PayoutRequest,
    PlanItem,
    ProductCreateRequest,
    ProductUpdateRequest,
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
        if "expect_version" in spec:
            assert request.headers.get("x-api-version") == spec["expect_version"], (
                "bad api version"
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


def test_create_payment_serializes_h2h_fields() -> None:
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
                        "returnUrl": "https://example.com/return",
                        "verificationUrl": "https://example.com/verify",
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
                "json": {"transaction": {"uid": "u1"}},
                "expect_body": {
                    "request": {
                        "amount": "700",
                        "currency": "USD",
                        "test": True,
                        "description": "Test transaction",
                        "trackingId": "tid",
                        "encryptedData": "jwe-blob",
                        "fiscalization": {
                            "externalId": "fisc-1",
                            "positions": [
                                {
                                    "name": "Product",
                                    "type": "service",
                                    "amount": 100,
                                    "quantity": 1.0,
                                    "measureUnitCode": 796,
                                    "description": "Desc",
                                    "untaxed": False,
                                    "nomenclatureCode": "code-1",
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


def test_create_payout_happy_path() -> None:
    c = client(
        {
            ("POST", "/transactions/payouts"): {
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
                }
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
