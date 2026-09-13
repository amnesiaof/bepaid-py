"""httpx-based client for the bePaid API (bepaid.by)."""

from __future__ import annotations

import base64
from typing import Any, Self

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

DEFAULT_GATEWAY_URL = "https://gateway.bepaid.by"
DEFAULT_CHECKOUT_URL = "https://checkout.bepaid.by"
DEFAULT_API_URL = "https://api.bepaid.by"

_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}


class BepaidClient:
    def __init__(
        self,
        shop_id: str | int,
        secret_key: str,
        *,
        timeout: float = 30.0,
        base_gateway_url: str = DEFAULT_GATEWAY_URL,
        base_checkout_url: str = DEFAULT_CHECKOUT_URL,
        base_api_url: str = DEFAULT_API_URL,
    ) -> None:
        credentials = f"{shop_id}:{secret_key}"
        self._auth = "Basic " + base64.b64encode(credentials.encode()).decode()
        self._base_gateway = base_gateway_url
        self._base_checkout = base_checkout_url
        self._base_api = base_api_url
        self._http = httpx.Client(timeout=timeout, headers=_HEADERS)

    @property
    def http(self) -> httpx.Client:
        """The underlying synchronous httpx client (for advanced use)."""
        return self._http

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── transport ──────────────────────────────────────────────────────────

    def _request(
        self, method: str, url: str, body: BaseModel | dict | None = None
    ) -> dict[str, Any]:
        resp = self._http.request(
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

    def create_payment(self, req: PaymentRequest) -> PaymentResponse:
        data = self._request(
            "POST",
            f"{self._base_gateway}/transactions/payments",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return PaymentResponse.model_validate(data["transaction"])

    def create_authorization(self, req: AuthorizationRequest) -> AuthorizationResponse:
        data = self._request(
            "POST",
            f"{self._base_gateway}/transactions/authorizations",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return AuthorizationResponse.model_validate(data["transaction"])

    def capture(self, req: CaptureRequest) -> CaptureResponse:
        data = self._request(
            "POST",
            f"{self._base_gateway}/transactions/captures",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return CaptureResponse.model_validate(data["transaction"])

    def void(self, req: VoidRequest) -> VoidResponse:
        data = self._request(
            "POST",
            f"{self._base_gateway}/transactions/voids",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return VoidResponse.model_validate(data["transaction"])

    def refund(self, req: RefundRequest) -> RefundResponse:
        data = self._request(
            "POST",
            f"{self._base_gateway}/transactions/refunds",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return RefundResponse.model_validate(data["transaction"])

    def get_transaction(self, uid: str) -> Transaction:
        data = self._request("GET", f"{self._base_gateway}/transactions/{uid}")
        return Transaction.model_validate(data["transaction"])

    # ── token API ──────────────────────────────────────────────────────────

    def create_token(self, req: CreateTokenRequest) -> TokenResponse:
        data = self._request(
            "POST",
            f"{self._base_gateway}/credit_cards",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return TokenResponse.model_validate(data)

    # ── checkout API ───────────────────────────────────────────────────────

    def create_checkout(self, req: CheckoutRequest) -> CheckoutResponse:
        data = self._request(
            "POST",
            f"{self._base_checkout}/ctp/api/checkouts",
            {"checkout": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return CheckoutResponse.model_validate(data["checkout"])

    def get_checkout_status(self, token: str) -> CheckoutStatus:
        data = self._request("GET", f"{self._base_checkout}/ctp/api/checkouts/{token}")
        return CheckoutStatus.model_validate(data["checkout"])

    def validate_apple_pay(self, url: str, token: str | None = None) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self._base_checkout}/ctp/api/apple_pay/validate",
            {"url": url, "token": token, "context": "merchant"},
        )

    # ── direct / APM API ───────────────────────────────────────────────────

    def create_apm_payment(self, req: ApmPaymentRequest) -> ApmPaymentResponse:
        data = self._request(
            "POST",
            f"{self._base_api}/beyag/transactions/payments",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return ApmPaymentResponse.model_validate(data["transaction"])

    def apm_refund(self, req: ApmRefundRequest) -> ApmRefundResponse:
        data = self._request(
            "POST",
            f"{self._base_api}/beyag/transactions/refunds",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return ApmRefundResponse.model_validate(data["transaction"])

    def apm_full_refund(
        self, parent_uid: str, reason: str, amount: int | None = None
    ) -> ApmRefundResponse:
        req = ApmRefundRequest(parent_uid=parent_uid, reason=reason, amount=amount)
        data = self._request(
            "POST",
            f"{self._base_api}/beyag/refunds",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return ApmRefundResponse.model_validate(data["transaction"])


# ── webhook helpers ──────────────────────────────────────────────────────────


def verify_webhook_auth(
    authorization_header: str, shop_id: str, secret_key: str
) -> bool:
    expected = "Basic " + base64.b64encode(f"{shop_id}:{secret_key}".encode()).decode()
    return authorization_header == expected
