"""Async client tests using the same mocked transport as the sync suite."""

from __future__ import annotations

import pytest
from test_client import (
    APM_BATCH7_CASES,
    ERIP_CASES,
    INTEGRATION_CASES,
    MASTERPASS_CASES,
    POLLING_INVALID_URLS,
    VISA_ALIAS_ERRORS,
    VISA_ALIAS_SUCCESS,
    MockTransport,
    apm_batch7_case,
    async_client,
    async_processing_flow,
    erip_case,
    integration_case,
    masterpass_case,
    masterpass_transaction_case,
    p2p_case,
    visa_alias_case,
)

from bepaid import AsyncBepaidClient, BepaidError, models
from bepaid.errors import ApiError
from bepaid.models import (
    ApmPaymentRequest,
    ApmPayoutRequest,
    ApmRefundRequest,
    AuthorizationRequest,
    BalanceRequest,
    ChargeCreditCard,
    ChargeRequest,
    CheckoutOrder,
    CheckoutOrderAdditionalData,
    CheckoutRequest,
    CheckupRequest,
    CurrencyQueryRequest,
    P2pRequest,
    PaymentRequest,
    PayoutCreditCard,
    PayoutRequest,
    ProductCreateRequest,
    ProductUpdateRequest,
    ProofDocument,
    ProofRequest,
    RecipientTokenizationRequest,
    ReportCountParams,
    ReportCountRequest,
    SplitAdditionalData,
    SplitCreditCard,
    SplitPaymentRequest,
    SubscriptionCreateRequest,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", MASTERPASS_CASES, ids=[c[0] for c in MASTERPASS_CASES])
@pytest.mark.parametrize("with_options", [False, True])
@pytest.mark.parametrize("outcome", ["success", "error", "empty"])
async def test_async_masterpass(case: tuple, with_options: bool, outcome: str) -> None:
    req, response_type, payload, handlers = masterpass_case(case, with_options, outcome)
    async with async_client(handlers) as c:
        response = await getattr(c, f"masterpass_{case[0]}")(req)
    assert isinstance(response, response_type)
    assert response.model_dump(exclude_none=True) == payload


@pytest.mark.asyncio
@pytest.mark.parametrize("case", MASTERPASS_CASES, ids=[c[0] for c in MASTERPASS_CASES])
async def test_async_masterpass_http_error(case: tuple) -> None:
    req, _, _, handlers = masterpass_case(case, False, "error")
    spec = handlers[("POST", f"/masterpass/{case[0]}")]
    spec.update(status=400, json={"message": "Invalid request"})
    async with async_client(handlers) as c:
        with pytest.raises(ApiError) as exc:
            await getattr(c, f"masterpass_{case[0]}")(req)
    assert exc.value.status == 400
    assert exc.value.message == "Invalid request"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["payment", "authorization"])
@pytest.mark.parametrize("status", ["successful", "failed"])
@pytest.mark.parametrize("result_status", ["successful", "failed"])
async def test_async_masterpass_transaction_metadata(
    operation: str, status: str, result_status: str
) -> None:
    req, response_type, additional_data, handlers = masterpass_transaction_case(
        operation, status, result_status
    )
    async with async_client(handlers) as c:
        response = await getattr(c, f"create_{operation}")(req)
    assert isinstance(response, response_type)
    assert response.additional_data == additional_data
    assert response.model_dump()["additional_data"] == additional_data
    assert response.status == status


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ERIP_CASES)
async def test_async_erip_contract(case: str) -> None:
    operation, args, payload, response_type, handlers = erip_case(case)
    async with async_client(handlers) as c:
        response = await getattr(c, operation)(*args)
    assert isinstance(response, response_type)
    assert (
        response
        if isinstance(response, (dict, list))
        else response.model_dump(exclude_unset=True)
    ) == payload


@pytest.mark.asyncio
@pytest.mark.parametrize("case", INTEGRATION_CASES)
async def test_async_integration_contract(case: str) -> None:
    operation, args, payload, response_type, handlers = integration_case(case)
    async with async_client(handlers) as c:
        result = await getattr(c, operation)(*args)
    assert isinstance(result, response_type)
    assert (
        result.model_dump(by_alias=True, exclude_unset=True) if result else None
    ) == payload


@pytest.mark.asyncio
async def test_async_processing_completed_flow() -> None:
    async with async_client(async_processing_flow()) as c:
        status = await c.get_async_status(
            "https://gateway.bepaid.by/async/status/integration-1"
        )
        assert isinstance(status, models.AsyncStatus)
        assert status.status == "completed"
        assert status.response_url is not None
        result = await c.get_async_result(status.response_url)
    assert isinstance(result, models.Transaction)
    assert result.uid == "integration-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["get_async_status", "get_async_result"])
@pytest.mark.parametrize("url", POLLING_INVALID_URLS)
async def test_async_polling_rejects_invalid_url(operation: str, url: str) -> None:
    async with AsyncBepaidClient(
        "test-shop",
        "test-secret",
        base_gateway_url="https://gateway.test",
        transport=MockTransport({}),
    ) as c:
        with pytest.raises(ValueError, match="configured gateway origin"):
            await getattr(c, operation)(url)


@pytest.mark.asyncio
async def test_async_erip_refund_requires_amount() -> None:
    async with async_client({}) as c:
        with pytest.raises(ValueError, match="amount"):
            await c.apm_full_refund("erip-1", "Client request")


@pytest.mark.asyncio
@pytest.mark.parametrize("case", APM_BATCH7_CASES)
async def test_async_apm_batch7_contract(case: str) -> None:
    operation, args, kwargs, payload, handlers = apm_batch7_case(case)
    async with async_client(handlers) as c:
        if case == "qiwi_error":
            with pytest.raises(ApiError) as exc:
                await getattr(c, operation)(*args, **kwargs)
            assert exc.value.status == 400
            assert exc.value.message == payload["message"]
            return
        result = await getattr(c, operation)(*args, **kwargs)
    assert (
        result if isinstance(result, dict) else result.model_dump(exclude_unset=True)
    ) == payload


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
                "expect_version": "3",
                "json": {
                    "transaction": {"tracking_id": "tracking_id_000", "uid": "u1"}
                },
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
                "expect_version": "3",
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
                "expect_version": "3",
                "json": {
                    "transaction": {
                        "uid": "b6c446e4",
                        "status": "incomplete",
                        "redirect_url": "https://gateway.bepaid.by/process/b6c446e4",
                    }
                },
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
async def test_async_transaction_status_by_tracking_id() -> None:
    c = async_client(
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
    try:
        t = await c.get_transaction_by_tracking_id("order-123")
        assert t.uid == "54c70f9b-e6e5-4b5a-bda2-fe6980e44bf0"
        assert t.transaction_status == "approved"
        assert t.billing_address is not None
        assert t.billing_address.city == "Denver"
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
@pytest.mark.parametrize("operation", ["create_p2p", "verify_p2p"])
async def test_async_p2p_preserves_full_payload(operation: str) -> None:
    req, payload, handlers = p2p_case(operation)
    async with async_client(handlers) as c:
        response = await getattr(c, operation)(req)
    assert response.model_dump(exclude_none=True) == payload


@pytest.mark.asyncio
async def test_async_visa_alias_success() -> None:
    req, handlers = visa_alias_case(VISA_ALIAS_SUCCESS)
    async with async_client(handlers) as c:
        response = await c.verify_visa_alias(req)
    assert isinstance(response, models.VisaAliasPhoneResponse)
    assert isinstance(response, models.CreditCardInfo)
    assert response.token == "visa-alias-token"
    assert response.service_info is not None
    assert response.service_info.issuer_name == "Test Bank"
    assert response.model_dump(by_alias=True, exclude_none=True) == VISA_ALIAS_SUCCESS


@pytest.mark.asyncio
@pytest.mark.parametrize("status,payload", VISA_ALIAS_ERRORS)
async def test_async_visa_alias_http_error(status: int, payload: dict) -> None:
    req, handlers = visa_alias_case(payload, status)
    async with async_client(handlers) as c:
        with pytest.raises(ApiError) as exc:
            await c.verify_visa_alias(req)
    assert exc.value.status == status
    assert exc.value.message == payload["message"]
    assert exc.value.errors == payload.get("errors")
    assert exc.value.error_code == payload.get("error_code")
    assert exc.value.code == payload["code"]
    assert exc.value.friendly_message == payload["friendly_message"]


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
                "expect_version": "3",
                "json": {
                    "transaction": {
                        "uid": "p2p1",
                        "status": "successful",
                        "type": "p2p",
                        "amount": 100,
                        "currency": "EUR",
                    }
                },
            },
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

        v = await c.verify_p2p(
            P2pRequest(
                amount=100,
                currency="USD",
                credit_card={"number": "4012001037141112"},
                recipient_card={"number": "4200000000000000"},
                test=True,
            )
        )
        assert v.status == "successful"
        assert v.commission is not None
        assert v.commission.currency == "USD"
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_async_payout_and_balance() -> None:
    c = async_client(
        {
            ("POST", "/transactions/payouts"): {
                "expect_version": "3",
                "json": {
                    "transaction": {
                        "uid": "1",
                        "type": "payout",
                        "status": "successful",
                        "amount": 100,
                        "currency": "USD",
                    }
                },
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


@pytest.mark.asyncio
async def test_async_apm_status_payout_proof_checkup() -> None:
    c = async_client(
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
            },
            ("GET", "/beyag/transactions/tracking_id/tracking_1"): {
                "json": {
                    "transactions": [
                        {"uid": "apm1", "type": "payment", "status": "successful"},
                        {"uid": "apm2", "type": "payment", "status": "failed"},
                    ]
                }
            },
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
            },
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
            },
            ("POST", "/beyag/gateways/mts_money_widget/check_service"): {
                "expect_version": "3",
                "json": {
                    "service_activated": True,
                    "message": None,
                    "validation": {"operator": "mts", "message": "OK"},
                },
            },
            ("GET", "/beyag/payments/ep1"): {
                "json": {
                    "transaction": {
                        "uid": "ep1",
                        "status": "pending",
                        "order_id": "633602201673",
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
            ("POST", "/transactions/checkups"): {
                "expect_version": "3",
                "json": {
                    "transaction": {
                        "uid": "c1",
                        "type": "payment",
                        "status": "successful",
                        "amount": 100,
                        "currency": "USD",
                    }
                },
            },
        }
    )
    try:
        t = await c.get_apm_transaction("apm1")
        assert t.status == "successful"

        ts = await c.get_apm_transactions_by_tracking_id("tracking_1")
        assert [x.uid for x in ts] == ["apm1", "apm2"]

        p = await c.apm_payout(
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

        r = await c.apm_proof(
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

        cu = await c.checkup(
            CheckupRequest(
                amount=100,
                currency="USD",
                description="checkup",
                tracking_id="tracking_1",
                credit_card=ChargeCreditCard(token="tok1"),
            )
        )
        assert cu.status == "successful"

        ms = await c.check_mts_service("375295222222", test=True)
        assert ms.service_activated is True
        assert ms.validation is not None
        assert ms.validation.operator == "mts"

        ep = await c.get_erip_payment("ep1")
        assert ep.status == "pending"
        ep = await c.get_erip_payment_by_order_id("633602201673")
        assert ep.uid == "ep2"
        ep = await c.delete_erip_payment("ep1")
        assert ep.status == "deleted"
    finally:
        await c.aclose()
