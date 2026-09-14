"""Async client tests using the same mocked transport as the sync suite."""

from __future__ import annotations

import pytest
from test_client import async_client

from bepaid import BepaidError
from bepaid.errors import ApiError
from bepaid.models import (
    ApmPaymentRequest,
    ApmRefundRequest,
    AuthorizationRequest,
    BalanceRequest,
    ChargeCreditCard,
    ChargeRequest,
    CheckoutOrder,
    CheckoutOrderAdditionalData,
    CheckoutRequest,
    CurrencyQueryRequest,
    P2pRequest,
    PaymentRequest,
    PayoutCreditCard,
    PayoutRequest,
    ProductCreateRequest,
    ProductUpdateRequest,
    RecipientTokenizationRequest,
    ReportCountParams,
    ReportCountRequest,
    SplitAdditionalData,
    SplitCreditCard,
    SplitPaymentRequest,
    SubscriptionCreateRequest,
)


def _payment_request() -> PaymentRequest:
    return PaymentRequest(
        amount="700",
        currency="USD",
        test=True,
        description="Test transaction",
        tracking_id="tracking_id_000",
    )


@pytest.mark.asyncio
async def test_async_create_payment() -> None:
    c = async_client(
        {
            ("POST", "/transactions/payments"): {
                "json": {"transaction": {"tracking_id": "tracking_id_000", "uid": "u1"}}
            }
        }
    )
    resp = await c.create_payment(_payment_request())
    assert resp.uid == "u1"
    await c.aclose()


@pytest.mark.asyncio
async def test_async_api_error() -> None:
    c = async_client(
        {
            ("POST", "/transactions/payments"): {
                "status": 400,
                "json": {"message": "Validation failed"},
            }
        }
    )
    with pytest.raises(ApiError) as exc:
        await c.create_payment(_payment_request())
    assert exc.value.status == 400
    await c.aclose()


@pytest.mark.asyncio
async def test_async_authorization_redirect() -> None:
    c = async_client(
        {
            ("POST", "/transactions/authorizations"): {
                "json": {
                    "transaction": {
                        "uid": "b6c446e4",
                        "status": "incomplete",
                        "redirect_url": "https://gateway.bepaid.by/process/b6c446e4",
                    }
                }
            }
        }
    )
    async with c:
        resp = await c.create_authorization(
            AuthorizationRequest(
                amount=100, currency="USD", description="Test", tracking_id="x"
            )
        )
        assert resp.redirect_url is not None
        assert resp.redirect_url.endswith("/process/b6c446e4")


@pytest.mark.asyncio
async def test_async_checkout_and_apm() -> None:
    c = async_client(
        {
            ("POST", "/ctp/api/checkouts"): {
                "json": {"checkout": {"token": "tok1", "redirect_url": "https://x"}}
            },
            ("POST", "/beyag/transactions/payments"): {
                "json": {
                    "transaction": {
                        "uid": "apm1",
                        "type": "payment",
                        "status": "pending",
                    }
                }
            },
            ("POST", "/beyag/transactions/refunds"): {
                "json": {"transaction": {"uid": "r1", "status": "successful"}}
            },
        }
    )
    try:
        co = await c.create_checkout(
            CheckoutRequest(
                test=True,
                order=CheckoutOrder(currency="USD", amount=7000, description="Test"),
            )
        )
        assert co.token == "tok1"
        p = await c.create_apm_payment(
            ApmPaymentRequest(
                amount=100,
                currency="BYN",
                ip="127.0.0.1",
                payment_method={"type": "mts_money", "confirm_agreement": "accept"},
            )
        )
        assert p.status == "pending"
        r = await c.apm_refund(ApmRefundRequest(parent_uid="apm1", reason="reason"))
        assert r.status == "successful"
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_async_payment_token() -> None:
    c = async_client(
        {
            ("POST", "/payments/tokens"): {
                "json": {
                    "checkout": {
                        "token": "3241e439f8c87d941d92621a4bdc030d",
                        "redirect_url": "https://checkout.bepaid.by/v2/checkout?token=3241e439",
                    }
                }
            }
        }
    )
    try:
        p = await c.create_payment_token(
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
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_async_charge_saved_card() -> None:
    c = async_client(
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
                    }
                },
            }
        }
    )
    try:
        resp = await c.charge_saved_card(
            ChargeRequest(
                amount=700,
                currency="USD",
                description="Saved card charge",
                credit_card=ChargeCreditCard(token="tok_123"),
            )
        )
        assert resp.uid == "1-310b0da80b"
        assert resp.status == "successful"
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_async_recipient_tokenization_and_apple_pay() -> None:
    c = async_client(
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
            },
            ("POST", "/apple_pay/payment"): {"json": {"Success": True, "Model": None}},
        }
    )
    try:
        tokenized = await c.tokenize_recipient_card(
            RecipientTokenizationRequest(
                description="Tokenize card",
                recipient_credit_card=PayoutCreditCard(
                    number="4242424242424242", holder="John Smith"
                ),
            )
        )
        assert tokenized["transaction"]["uid"] == "1-310b0da80b"
        apple = await c.apple_pay_payment("eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9...")
        assert apple["Success"] is True
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_async_errors_baseclass() -> None:
    assert issubclass(ApiError, BepaidError)


@pytest.mark.asyncio
async def test_async_subscriptions_and_p2p() -> None:
    c = async_client(
        {
            ("POST", "/subscriptions"): {
                "json": {
                    "id": "sbs_cce60e7f2d661bc0",
                    "state": "active",
                    "card": {"brand": "master", "last_4": "5003", "token": "tok_1"},
                    "plan": {"id": "pln_1", "title": "Basic plan"},
                }
            },
            ("POST", "/transactions/p2ps"): {
                "json": {
                    "transaction": {
                        "uid": "p2p1",
                        "status": "successful",
                        "type": "p2p",
                        "amount": 100,
                        "currency": "EUR",
                    }
                }
            },
        }
    )
    try:
        s = await c.create_subscription(
            SubscriptionCreateRequest(
                card={"token": "tok_1"},
                plan={"id": "pln_1"},
                tracking_id="async_track",
            )
        )
        assert s.state == "active"
        p = await c.create_p2p(
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
        assert p.status == "successful"
        assert p.type == "p2p"
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_async_payout_and_balance() -> None:
    c = async_client(
        {
            ("POST", "/transactions/payouts"): {
                "json": {
                    "transaction": {
                        "uid": "1",
                        "type": "payout",
                        "status": "successful",
                        "amount": 100,
                        "currency": "USD",
                    }
                }
            },
            ("POST", "/beyag/balance"): {
                "json": {
                    "status": "Successful",
                    "code": "S.0000",
                    "gateway_id": 1234,
                    "amount": 1290092162,
                    "currency": "USD",
                }
            },
        }
    )
    try:
        p = await c.create_payout(
            PayoutRequest(
                amount=100,
                currency="USD",
                recipient={"ip": "127.0.0.1", "email": "john@example.com"},
                sender={"ip": "127.0.0.1", "email": "john@example.com"},
                recipient_billing_address={"country": "US", "city": "Denver"},
                sender_billing_address={"country": "US", "city": "Denver"},
            )
        )
        assert p.status == "successful"
        assert p.type == "payout"
        b = await c.get_balance(BalanceRequest(gateway_id=1234, currency="USD"))
        assert b.amount == 1290092162
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_async_report_count() -> None:
    c = async_client(
        {
            ("POST", "/api/reports/count"): {
                "expect_version": "3",
                "json": {"transactions": {"count": 2}},
            }
        }
    )
    try:
        r = await c.get_report_count(
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
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_async_split_payment() -> None:
    c = async_client(
        {
            ("POST", "/splits/payment"): {
                "json": {
                    "splits": [
                        {
                            "uid": "21-99834feb0b",
                            "amount": 70,
                            "shop_id": 91,
                            "parent": True,
                        },
                        {
                            "uid": "22-56784ffecd",
                            "amount": 30,
                            "shop_id": 1111,
                            "parent": False,
                        },
                    ]
                }
            }
        }
    )
    try:
        r = await c.create_split_payment(
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
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_async_products() -> None:
    product = {
        "id": "prd_ed27b047d3ccd1a6",
        "name": "product",
        "description": "description",
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
    c = async_client(
        {
            ("POST", "/products"): {"json": product},
            ("GET", "/products"): {"json": [product]},
            ("PUT", "/products/prd_1"): {"status": 204},
            ("GET", "/plans/pln_a134847c902551de/pay"): {
                "json": {"redirect_url": "https://checkout.bepaid.by/pay?token=abc"}
            },
        }
    )
    try:
        created = await c.create_product(
            ProductCreateRequest(
                name="product",
                description="description",
                currency="USD",
                amount=990,
                quantity="10",
            )
        )
        assert created.id == "prd_ed27b047d3ccd1a6"
        listed = await c.list_products()
        assert len(listed) == 1
        await c.update_product("prd_1", ProductUpdateRequest(amount=950, quantity="5"))
        link = await c.get_plan_payment_link("pln_a134847c902551de")
        assert link["redirect_url"] == "https://checkout.bepaid.by/pay?token=abc"
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_async_currency_query() -> None:
    c = async_client(
        {
            ("POST", "/beyag/currencies"): {
                "json": {
                    "status": "Successful",
                    "code": "S.0000",
                    "gateway_id": 1234,
                    "country": "GB",
                    "currency": "TRX",
                    "provider_info": {"networks": [{"name": "tron"}]},
                }
            }
        }
    )
    try:
        info = await c.get_currencies(
            CurrencyQueryRequest(gateway_id=1234, account="40701810842020395221")
        )
        assert info.status == "Successful"
        assert info.currency == "TRX"
        assert info.provider_info is not None
        assert info.provider_info["networks"][0]["name"] == "tron"
    finally:
        await c.aclose()
