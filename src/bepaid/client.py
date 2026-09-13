"""httpx-based client for the bePaid API (bepaid.by)."""

from __future__ import annotations

import asyncio
import base64
import sys
from collections.abc import Coroutine
from typing import Any, TypeVar

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from pydantic import BaseModel

from .errors import ApiError
from .models import (
    ApmConfirmRequest,
    ApmConfirmResponse,
    ApmPaymentRequest,
    ApmPaymentResponse,
    ApmRefundRequest,
    ApmRefundResponse,
    AuthorizationRequest,
    AuthorizationResponse,
    BalanceRequest,
    BalanceResponse,
    CancelSubscriptionRequest,
    CaptureRequest,
    CaptureResponse,
    ChannelBalance,
    ChargeRequest,
    CheckoutRequest,
    CheckoutResponse,
    CheckoutStatus,
    CreateTokenRequest,
    CustomerRecord,
    P2pRequest,
    P2pResponse,
    PaymentRequest,
    PaymentResponse,
    PayoutRequest,
    PayoutResponse,
    PlanItem,
    Product,
    ProductCreateRequest,
    ProductUpdateRequest,
    RefundRequest,
    RefundResponse,
    ReportCountRequest,
    ReportCountResponse,
    ReportListRequest,
    ReportListResponse,
    SplitPaymentRequest,
    SplitPaymentResponse,
    Subscription,
    SubscriptionCreateRequest,
    TokenResponse,
    Transaction,
    VoidRequest,
    VoidResponse,
)

T = TypeVar("T")

DEFAULT_GATEWAY_URL = "https://gateway.bepaid.by"
DEFAULT_CHECKOUT_URL = "https://checkout.bepaid.by"
DEFAULT_API_URL = "https://api.bepaid.by"
DEFAULT_MERCHANT_URL = "https://merchant.bepaid.by"

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
        base_merchant_url: str = DEFAULT_MERCHANT_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        credentials = f"{shop_id}:{secret_key}"
        self._auth = "Basic " + base64.b64encode(credentials.encode()).decode()
        self._base_gateway = base_gateway_url
        self._base_checkout = base_checkout_url
        self._base_api = base_api_url
        self._base_merchant = base_merchant_url
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
        self,
        method: str,
        url: str,
        body: BaseModel | dict | None = None,
        api_version: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": self._auth}
        if api_version is not None:
            headers["X-Api-Version"] = api_version
        resp = await self._http.request(
            method,
            url,
            headers=headers,
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
        if not resp.content:
            return {}
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

    # ── saved-card charges ─────────────────────────────────────────────────

    async def charge_saved_card(self, req: ChargeRequest) -> Transaction:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/services/credit_cards/charges",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            api_version="3",
        )
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

    async def create_payment_token(self, req: CheckoutRequest) -> CheckoutResponse:
        data = await self._request(
            "POST",
            f"{self._base_api}/payments/tokens",
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

    async def confirm_apm_payment(
        self, uid: str, req: ApmConfirmRequest
    ) -> ApmConfirmResponse:
        data = await self._request(
            "POST",
            f"{self._base_api}/beyag/transactions/{uid}/confirm",
            req.model_dump(by_alias=True, exclude_none=True),
        )
        return ApmConfirmResponse.model_validate(data["response"])

    # ── P2P transfer ───────────────────────────────────────────────────────

    async def create_p2p(self, req: P2pRequest) -> P2pResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/transactions/p2ps",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return P2pResponse.model_validate(data["transaction"])

    # ── subscriptions API ──────────────────────────────────────────────────

    async def create_customer(self, req: CustomerRecord) -> CustomerRecord:
        data = await self._request(
            "POST",
            f"{self._base_api}/customers",
            req.model_dump(by_alias=True, exclude_none=True),
        )
        return CustomerRecord.model_validate(data)

    async def get_customer(self, id: str) -> CustomerRecord:
        data = await self._request("GET", f"{self._base_api}/customers/{id}")
        return CustomerRecord.model_validate(data)

    async def list_customers(self) -> list[CustomerRecord]:
        data = await self._request("GET", f"{self._base_api}/customers")
        return [CustomerRecord.model_validate(item) for item in data]

    async def create_plan(self, req: PlanItem) -> PlanItem:
        data = await self._request(
            "POST",
            f"{self._base_api}/plans",
            req.model_dump(by_alias=True, exclude_none=True),
        )
        return PlanItem.model_validate(data)

    async def get_plan(self, id: str) -> PlanItem:
        data = await self._request("GET", f"{self._base_api}/plans/{id}")
        return PlanItem.model_validate(data)

    async def list_plans(self) -> list[PlanItem]:
        data = await self._request("GET", f"{self._base_api}/plans")
        return [PlanItem.model_validate(item) for item in data]

    async def create_subscription(self, req: SubscriptionCreateRequest) -> Subscription:
        data = await self._request(
            "POST",
            f"{self._base_api}/subscriptions",
            req.model_dump(by_alias=True, exclude_none=True),
        )
        return Subscription.model_validate(data)

    async def get_subscription(self, id: str) -> Subscription:
        data = await self._request("GET", f"{self._base_api}/subscriptions/{id}")
        return Subscription.model_validate(data)

    async def cancel_subscription(
        self, id: str, req: CancelSubscriptionRequest
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"{self._base_api}/subscriptions/{id}/cancel",
            req.model_dump(by_alias=True, exclude_none=True),
        )

    async def get_plan_payment_link(self, plan_id: str) -> dict[str, Any]:
        return await self._request("GET", f"{self._base_api}/plans/{plan_id}/pay")

    # ── payout ─────────────────────────────────────────────────────────────

    async def create_payout(self, req: PayoutRequest) -> PayoutResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/transactions/payouts",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return PayoutResponse.model_validate(data["transaction"])

    # ── APM balance query ───────────────────────────────────────────────────

    async def get_balance(self, req: BalanceRequest) -> BalanceResponse:
        data = await self._request(
            "POST",
            f"{self._base_api}/beyag/balance",
            req.model_dump(by_alias=True, exclude_none=True),
        )
        return BalanceResponse.model_validate(data)

    # ── merchant reports ────────────────────────────────────────────────────

    async def get_reports(self, req: ReportListRequest) -> ReportListResponse:
        data = await self._request(
            "POST",
            f"{self._base_merchant}/api/reports",
            req.model_dump(by_alias=True, exclude_none=True),
            api_version="2",
        )
        return ReportListResponse.model_validate(data)

    async def get_report_count(self, req: ReportCountRequest) -> ReportCountResponse:
        data = await self._request(
            "POST",
            f"{self._base_merchant}/api/reports/count",
            req.model_dump(by_alias=True, exclude_none=True),
            api_version="3",
        )
        return ReportCountResponse.model_validate(data)

    async def get_channel_balances(
        self, gateway_id: int, currency: str | None = None
    ) -> list[ChannelBalance]:
        suffix = f"&currency={currency}" if currency else ""
        data = await self._request(
            "GET",
            f"{self._base_merchant}/shop/channel_balances/?gateway_id={gateway_id}{suffix}",
        )
        return [ChannelBalance.model_validate(item) for item in data]

    # ── split payments ──────────────────────────────────────────────────────

    async def create_split_payment(
        self, req: SplitPaymentRequest
    ) -> SplitPaymentResponse:
        data = await self._request(
            "POST",
            f"{self._base_api}/splits/payment",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return SplitPaymentResponse.model_validate(data)

    # ── pay-by-link products ────────────────────────────────────────────────

    async def create_product(self, req: ProductCreateRequest) -> Product:
        data = await self._request(
            "POST",
            f"{self._base_api}/products",
            req.model_dump(by_alias=True, exclude_none=True),
        )
        return Product.model_validate(data)

    async def list_products(self) -> list[Product]:
        data = await self._request("GET", f"{self._base_api}/products")
        return [Product.model_validate(item) for item in data]

    async def get_product(self, product_id: str) -> Product:
        data = await self._request(
            "GET",
            f"{self._base_api}/products/{product_id}",
        )
        return Product.model_validate(data)

    async def update_product(self, product_id: str, req: ProductUpdateRequest) -> None:
        await self._request(
            "PUT",
            f"{self._base_api}/products/{product_id}",
            req.model_dump(by_alias=True, exclude_none=True),
        )


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
        base_merchant_url: str = DEFAULT_MERCHANT_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._shop_id = shop_id
        self._secret_key = secret_key
        self._timeout = timeout
        self._base_gateway = base_gateway_url
        self._base_checkout = base_checkout_url
        self._base_api = base_api_url
        self._base_merchant = base_merchant_url
        self._transport = transport

    def _run(self, coro: Coroutine[Any, Any, T]) -> T:
        return asyncio.run(coro)

    def _client(self) -> AsyncBepaidClient:
        return AsyncBepaidClient(
            self._shop_id,
            self._secret_key,
            timeout=self._timeout,
            base_gateway_url=self._base_gateway,
            base_checkout_url=self._base_checkout,
            base_api_url=self._base_api,
            base_merchant_url=self._base_merchant,
            transport=self._transport,
        )

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

    # ── saved-card charges ─────────────────────────────────────────────────

    def charge_saved_card(self, req: ChargeRequest) -> Transaction:
        return self._invoke("charge_saved_card", req)

    # ── token API ──────────────────────────────────────────────────────────

    def create_token(self, req: CreateTokenRequest) -> TokenResponse:
        return self._invoke("create_token", req)

    # ── checkout API ───────────────────────────────────────────────────────

    def create_checkout(self, req: CheckoutRequest) -> CheckoutResponse:
        return self._invoke("create_checkout", req)

    def create_payment_token(self, req: CheckoutRequest) -> CheckoutResponse:
        return self._invoke("create_payment_token", req)

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

    def confirm_apm_payment(
        self, uid: str, req: ApmConfirmRequest
    ) -> ApmConfirmResponse:
        return self._invoke("confirm_apm_payment", uid, req)

    # ── P2P transfer ───────────────────────────────────────────────────────

    def create_p2p(self, req: P2pRequest) -> P2pResponse:
        return self._invoke("create_p2p", req)

    # ── subscriptions API ──────────────────────────────────────────────────

    def create_customer(self, req: CustomerRecord) -> CustomerRecord:
        return self._invoke("create_customer", req)

    def get_customer(self, id: str) -> CustomerRecord:
        return self._invoke("get_customer", id)

    def list_customers(self) -> list[CustomerRecord]:
        return self._invoke("list_customers")

    def create_plan(self, req: PlanItem) -> PlanItem:
        return self._invoke("create_plan", req)

    def get_plan(self, id: str) -> PlanItem:
        return self._invoke("get_plan", id)

    def list_plans(self) -> list[PlanItem]:
        return self._invoke("list_plans")

    def create_subscription(self, req: SubscriptionCreateRequest) -> Subscription:
        return self._invoke("create_subscription", req)

    def get_subscription(self, id: str) -> Subscription:
        return self._invoke("get_subscription", id)

    def cancel_subscription(
        self, id: str, req: CancelSubscriptionRequest
    ) -> dict[str, Any]:
        return self._invoke("cancel_subscription", id, req)

    def get_plan_payment_link(self, plan_id: str) -> dict[str, Any]:
        return self._invoke("get_plan_payment_link", plan_id)

    # ── payout ─────────────────────────────────────────────────────────────

    def create_payout(self, req: PayoutRequest) -> PayoutResponse:
        return self._invoke("create_payout", req)

    # ── APM balance query ───────────────────────────────────────────────────

    def get_balance(self, req: BalanceRequest) -> BalanceResponse:
        return self._invoke("get_balance", req)

    # ── merchant reports ────────────────────────────────────────────────────

    def get_reports(self, req: ReportListRequest) -> ReportListResponse:
        return self._invoke("get_reports", req)

    def get_report_count(self, req: ReportCountRequest) -> ReportCountResponse:
        return self._invoke("get_report_count", req)

    def get_channel_balances(
        self, gateway_id: int, currency: str | None = None
    ) -> list[ChannelBalance]:
        return self._invoke("get_channel_balances", gateway_id, currency)

    # ── split payments ──────────────────────────────────────────────────────

    def create_split_payment(self, req: SplitPaymentRequest) -> SplitPaymentResponse:
        return self._invoke("create_split_payment", req)

    # ── pay-by-link products ────────────────────────────────────────────────

    def create_product(self, req: ProductCreateRequest) -> Product:
        return self._invoke("create_product", req)

    def list_products(self) -> list[Product]:
        return self._invoke("list_products")

    def get_product(self, product_id: str) -> Product:
        return self._invoke("get_product", product_id)

    def update_product(self, product_id: str, req: ProductUpdateRequest) -> None:
        self._invoke("update_product", product_id, req)


# ── webhook helpers ──────────────────────────────────────────────────────────


def verify_webhook_auth(
    authorization_header: str, shop_id: str, secret_key: str
) -> bool:
    expected = "Basic " + base64.b64encode(f"{shop_id}:{secret_key}".encode()).decode()
    return authorization_header == expected


def verify_webhook_signature(
    public_key_pem: str, signature: str, raw_body: bytes
) -> bool:
    """Verify the RSA-SHA256 ``Content-Signature`` of a bePaid webhook.

    ``public_key_pem`` is the shop's public key from the bePaid dashboard,
    ``signature`` is the base64 ``Content-Signature`` header value, and
    ``raw_body`` is the raw UTF-8 body bytes of the notification. Returns
    ``True`` for a genuine signature, ``False`` when it does not match.
    """
    public_key = serialization.load_pem_public_key(public_key_pem.encode())
    if not isinstance(public_key, rsa.RSAPublicKey):
        return False
    decoded = base64.b64decode(signature)
    try:
        public_key.verify(decoded, raw_body, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        return False
    return True
