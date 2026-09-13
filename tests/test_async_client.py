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
    CheckoutOrder,
    CheckoutRequest,
    PaymentRequest,
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
async def test_async_errors_baseclass() -> None:
    assert issubclass(ApiError, BepaidError)
