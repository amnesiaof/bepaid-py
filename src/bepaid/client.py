"""httpx-based client for the bePaid API (bepaid.by)."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable
from typing import Any, Self, TypeVar

import httpx
from pydantic import BaseModel

from .errors import ApiError
from .models import (
    ApmPaymentRequest,
    ApmPaymentResponse,
    ApmRefundRequest,
    ApmRefundResponse,
    AuthorizationRequest,
    AuthorizationResponse,
    CaptureRequest,
    CaptureResponse,
    CheckoutRequest,
    CheckoutResponse,
    CheckoutStatus,
    CreateTokenRequest,
    PaymentRequest,
    PaymentResponse,
    RefundRequest,
    RefundResponse,
    TokenResponse,
    Transaction,
    VoidRequest,
    VoidResponse,
)

T = TypeVar("T")

DEFAULT_GATEWAY_URL = "https://gateway.bepaid.by"
DEFAULT_CHECKOUT_URL = "https://checkout.bepaid.by"
DEFAULT_API_URL = "https://api.bepaid.by"

_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}


class AsyncBepaidClient:
    """Async client for the bePaid API. This is the single implementation of
    all request logic; :class:`BepaidClient` wraps it for synchronous use.
    """

    def __init__(
        self,
        shop_id: str | int,
        secret_key: str,
        *,
        timeout: float = 30.0,
        base_gateway_url: str = DEFAULT_GATEWAY_URL,
        base_checkout_url: str = DEFAULT_CHECKOUT_URL,
        base_api_url: str = DEFAULT_API_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        credentials = f"{shop_id}:{secret_key}"
        self._auth = "Basic " + base64.b64encode(credentials.encode()).decode()
        self._base_gateway = base_gateway_url
        self._base_checkout = base_checkout_url
        self._base_api = base_api_url
        self._http = httpx.AsyncClient(
            transport=transport,
            timeout=timeout,
            headers=_HEADERS,
        )

    @property
    def http(self) -> httpx.AsyncClient:
        """The underlying httpx async client (for advanced use)."""
        return self._http

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # ── transport ──────────────────────────────────────────────────────────

    async def _request(
        self, method: str, url: str, body: BaseModel | dict | None = None
    ) -> dict[str, Any]:
        resp = await self._http.request(
            method,
            url,
            headers={"Authorization": self._auth},
            json=body.model_dump(by_alias=True, exclude_none=True)
            if isinstance(body, BaseModel)
            else body,
        )
        if resp.status_code >= 400:
            data = resp.json()
            raise ApiError(
                status=resp.status_code,
                message=data.get("message", resp.text),
                errors=data.get("errors"),
            )
        return resp.json()

    # ── gateway API ────────────────────────────────────────────────────────

    async def create_payment(self, req: PaymentRequest) -> PaymentResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/transactions/payments",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return PaymentResponse.model_validate(data["transaction"])

    async def create_authorization(
        self, req: AuthorizationRequest
    ) -> AuthorizationResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/transactions/authorizations",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return AuthorizationResponse.model_validate(data["transaction"])

    async def capture(self, req: CaptureRequest) -> CaptureResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/transactions/captures",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return CaptureResponse.model_validate(data["transaction"])

    async def void(self, req: VoidRequest) -> VoidResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/transactions/voids",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return VoidResponse.model_validate(data["transaction"])

    async def refund(self, req: RefundRequest) -> RefundResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/transactions/refunds",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return RefundResponse.model_validate(data["transaction"])

    async def get_transaction(self, uid: str) -> Transaction:
        data = await self._request("GET", f"{self._base_gateway}/transactions/{uid}")
        return Transaction.model_validate(data["transaction"])

    # ── token API ──────────────────────────────────────────────────────────

    async def create_token(self, req: CreateTokenRequest) -> TokenResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/credit_cards",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return TokenResponse.model_validate(data)

    # ── checkout API ───────────────────────────────────────────────────────

    async def create_checkout(self, req: CheckoutRequest) -> CheckoutResponse:
        data = await self._request(
            "POST",
            f"{self._base_checkout}/ctp/api/checkouts",
            {"checkout": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return CheckoutResponse.model_validate(data["checkout"])

    async def get_checkout_status(self, token: str) -> CheckoutStatus:
        data = await self._request(
            "GET", f"{self._base_checkout}/ctp/api/checkouts/{token}"
        )
        return CheckoutStatus.model_validate(data["checkout"])

    async def validate_apple_pay(
        self, url: str, token: str | None = None
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"{self._base_checkout}/ctp/api/apple_pay/validate",
            {"url": url, "token": token, "context": "merchant"},
        )

    # ── direct / APM API ───────────────────────────────────────────────────

    async def create_apm_payment(self, req: ApmPaymentRequest) -> ApmPaymentResponse:
        data = await self._request(
            "POST",
            f"{self._base_api}/beyag/transactions/payments",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return ApmPaymentResponse.model_validate(data["transaction"])

    async def apm_refund(self, req: ApmRefundRequest) -> ApmRefundResponse:
        data = await self._request(
            "POST",
            f"{self._base_api}/beyag/transactions/refunds",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return ApmRefundResponse.model_validate(data["transaction"])

    async def apm_full_refund(
        self, parent_uid: str, reason: str, amount: int | None = None
    ) -> ApmRefundResponse:
        req = ApmRefundRequest(parent_uid=parent_uid, reason=reason, amount=amount)
        data = await self._request(
            "POST",
            f"{self._base_api}/beyag/refunds",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return ApmRefundResponse.model_validate(data["transaction"])


class BepaidClient:
    """Synchronous wrapper around :class:`AsyncBepaidClient`.

    Each call runs on a fresh event loop (via :func:`asyncio.run`), so the
    wrapper does not reuse persistent connections. Prefer AsyncBepaidClient
    when you are already in an asyncio application.
    """

    def __init__(
        self,
        shop_id: str | int,
        secret_key: str,
        *,
        timeout: float = 30.0,
        base_gateway_url: str = DEFAULT_GATEWAY_URL,
        base_checkout_url: str = DEFAULT_CHECKOUT_URL,
        base_api_url: str = DEFAULT_API_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client_kw = {
            "shop_id": shop_id,
            "secret_key": secret_key,
            "timeout": timeout,
            "base_gateway_url": base_gateway_url,
            "base_checkout_url": base_checkout_url,
            "base_api_url": base_api_url,
            "transport": transport,
        }

    def _run(self, coro: Awaitable[T]) -> T:
        return asyncio.run(coro)

    def _client(self) -> AsyncBepaidClient:
        return AsyncBepaidClient(**self._client_kw)

    async def _call(self, operation: str, *args: object) -> Any:
        async with self._client() as client:
            return await getattr(client, operation)(*args)

    def _invoke(self, operation: str, *args: object) -> Any:
        return self._run(self._call(operation, *args))

    # ── gateway API ────────────────────────────────────────────────────────

    def create_payment(self, req: PaymentRequest) -> PaymentResponse:
        return self._invoke("create_payment", req)

    def create_authorization(self, req: AuthorizationRequest) -> AuthorizationResponse:
        return self._invoke("create_authorization", req)

    def capture(self, req: CaptureRequest) -> CaptureResponse:
        return self._invoke("capture", req)

    def void(self, req: VoidRequest) -> VoidResponse:
        return self._invoke("void", req)

    def refund(self, req: RefundRequest) -> RefundResponse:
        return self._invoke("refund", req)

    def get_transaction(self, uid: str) -> Transaction:
        return self._invoke("get_transaction", uid)

    # ── token API ──────────────────────────────────────────────────────────

    def create_token(self, req: CreateTokenRequest) -> TokenResponse:
        return self._invoke("create_token", req)

    # ── checkout API ───────────────────────────────────────────────────────

    def create_checkout(self, req: CheckoutRequest) -> CheckoutResponse:
        return self._invoke("create_checkout", req)

    def get_checkout_status(self, token: str) -> CheckoutStatus:
        return self._invoke("get_checkout_status", token)

    def validate_apple_pay(self, url: str, token: str | None = None) -> dict[str, Any]:
        return self._invoke("validate_apple_pay", url, token)

    # ── direct / APM API ───────────────────────────────────────────────────

    def create_apm_payment(self, req: ApmPaymentRequest) -> ApmPaymentResponse:
        return self._invoke("create_apm_payment", req)

    def apm_refund(self, req: ApmRefundRequest) -> ApmRefundResponse:
        return self._invoke("apm_refund", req)

    def apm_full_refund(
        self, parent_uid: str, reason: str, amount: int | None = None
    ) -> ApmRefundResponse:
        return self._invoke("apm_full_refund", parent_uid, reason, amount)


# ── webhook helpers ──────────────────────────────────────────────────────────


def verify_webhook_auth(
    authorization_header: str, shop_id: str, secret_key: str
) -> bool:
    expected = "Basic " + base64.b64encode(f"{shop_id}:{secret_key}".encode()).decode()
    return authorization_header == expected
