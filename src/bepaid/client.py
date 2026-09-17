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
from pydantic import BaseModel, TypeAdapter

from .errors import ApiError
from .models import (
    ApmConfirmRequest,
    ApmConfirmResponse,
    ApmPaymentRequest,
    ApmPaymentResponse,
    ApmPayoutRequest,
    ApmPayoutResponse,
    ApmRefundRequest,
    ApmRefundResponse,
    AsyncAck,
    AsyncStatus,
    AuthorizationRequest,
    BalanceRequest,
    BalanceResponse,
    CancelSubscriptionRequest,
    CaptureRequest,
    CaptureResponse,
    CardBalanceRequest,
    CardBalanceResponse,
    ChannelBalance,
    ChargeRequest,
    CheckoutRequest,
    CheckoutResponse,
    CheckoutStatus,
    CheckServiceResponse,
    CheckupRequest,
    CreateTokenRequest,
    CurrencyInfo,
    CurrencyQueryRequest,
    CustomerRecord,
    EripPayListRequest,
    MasterpassCardResponse,
    MasterpassDeleteCardRequest,
    MasterpassDeleteCardResponse,
    MasterpassGetCardRequest,
    MasterpassGetCardsRequest,
    MasterpassGetCardsResponse,
    MasterpassGetSavedCardRequest,
    MasterpassLoginRequest,
    MasterpassLoginResponse,
    P2pRequest,
    P2pResponse,
    PaymentRequest,
    PayoutRequest,
    PayoutResponse,
    PlanItem,
    Product,
    ProductCreateRequest,
    ProductUpdateRequest,
    ProofRequest,
    ProofResponse,
    RecipientTokenizationRequest,
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
    TokenizationRequest,
    TokenResponse,
    TrackingIdStatus,
    Transaction,
    VerifyP2pResponse,
    VisaAliasPhoneRequest,
    VisaAliasPhoneResponse,
    VoidRequest,
    VoidResponse,
    WebhookNotification,
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
        self._auth = _basic_auth_header(str(shop_id), secret_key)
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
        request_id: str | None = None,
        *,
        polling: bool = False,
    ) -> Any:
        if polling:
            try:
                destination = httpx.URL(url)
                gateway = httpx.URL(self._base_gateway)
            except httpx.InvalidURL:
                raise ValueError(
                    "polling URL must use the configured gateway origin"
                ) from None
            if (
                destination.scheme not in ("http", "https")
                or not destination.host
                or destination.userinfo
                or "@" in url.partition("://")[2].split("/", 1)[0].split("?", 1)[0]
                or any(
                    char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url
                )
                or "\\" in url
                or "#" in url
                or (destination.scheme, destination.host, destination.port)
                != (gateway.scheme, gateway.host, gateway.port)
            ):
                raise ValueError("polling URL must use the configured gateway origin")
        headers = {"Authorization": self._auth}
        if api_version is not None:
            headers["X-Api-Version"] = api_version
        if request_id is not None:
            headers["RequestID"] = request_id
        resp = await self._http.request(
            method,
            url,
            headers=headers,
            json=body.model_dump(by_alias=True, exclude_none=True)
            if isinstance(body, BaseModel)
            else body,
            follow_redirects=False if polling else self._http.follow_redirects,
        )
        if polling and 300 <= resp.status_code < 400:
            raise ApiError(resp.status_code, "polling redirects are not allowed")
        if resp.status_code >= 400:
            data = resp.json()
            raise ApiError(
                status=resp.status_code,
                message=data.get("message", resp.text),
                errors=data.get("errors"),
                error_code=data.get("error_code"),
                code=data.get("code"),
                friendly_message=data.get("friendly_message"),
            )
        if not resp.content:
            return {}
        return resp.json()

    # ── gateway API ────────────────────────────────────────────────────────

    async def create_payment(
        self, req: PaymentRequest, request_id: str | None = None
    ) -> Transaction:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/transactions/payments",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            api_version="3",
            request_id=request_id,
        )
        return Transaction.model_validate(data["transaction"])

    async def create_authorization(
        self, req: AuthorizationRequest, request_id: str | None = None
    ) -> Transaction:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/transactions/authorizations",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            api_version="3",
            request_id=request_id,
        )
        return Transaction.model_validate(data["transaction"])

    async def create_payment_async(
        self, req: PaymentRequest, request_id: str | None = None
    ) -> AsyncAck:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/async/transactions/payments",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            api_version="3",
            request_id=request_id,
        )
        return AsyncAck.model_validate(data)

    async def create_authorization_async(
        self, req: AuthorizationRequest, request_id: str | None = None
    ) -> AsyncAck:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/async/transactions/authorizations",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            api_version="3",
            request_id=request_id,
        )
        return AsyncAck.model_validate(data)

    async def get_async_status(self, url: str) -> AsyncStatus:
        data = await self._request("GET", url, polling=True)
        return AsyncStatus.model_validate(data)

    async def get_async_result(self, url: str) -> Transaction:
        data = await self._request("GET", url, polling=True)
        return Transaction.model_validate(data["transaction"])

    async def get_card_balance(self, req: CardBalanceRequest) -> CardBalanceResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/balance",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            api_version="2",
        )
        return CardBalanceResponse.model_validate(data)

    async def capture(
        self, req: CaptureRequest, request_id: str | None = None
    ) -> CaptureResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/transactions/captures",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            api_version="3",
            request_id=request_id,
        )
        return CaptureResponse.model_validate(data["transaction"])

    async def void(
        self, req: VoidRequest, request_id: str | None = None
    ) -> VoidResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/transactions/voids",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            api_version="3",
            request_id=request_id,
        )
        return VoidResponse.model_validate(data["transaction"])

    async def refund(
        self, req: RefundRequest, request_id: str | None = None
    ) -> RefundResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/transactions/refunds",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            api_version="3",
            request_id=request_id,
        )
        return RefundResponse.model_validate(data["transaction"])

    async def get_transaction(self, uid: str) -> Transaction:
        data = await self._request(
            "GET", f"{self._base_gateway}/transactions/{uid}", api_version="3"
        )
        return Transaction.model_validate(data["transaction"])

    async def get_transaction_by_tracking_id(
        self, tracking_id: str
    ) -> TrackingIdStatus:
        data = await self._request(
            "GET",
            f"{self._base_gateway}/v2/transactions/tracking_id/{tracking_id}",
        )
        return TrackingIdStatus.model_validate(data)

    # ── saved-card charges ─────────────────────────────────────────────────

    async def charge_saved_card(
        self, req: ChargeRequest, request_id: str | None = None
    ) -> Transaction:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/services/credit_cards/charges",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            api_version="3",
            request_id=request_id,
        )
        return Transaction.model_validate(data["transaction"])

    # ── recipient tokenization ─────────────────────────────────────────────

    async def tokenize_recipient_card(
        self, req: RecipientTokenizationRequest
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"{self._base_gateway}/transactions/recipient_tokenizations",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            api_version="3",
        )

    # ── Apple Pay ──────────────────────────────────────────────────────────

    async def apple_pay_payment(self, token: str) -> dict[str, Any]:
        return await self._request(
            "POST", f"{self._base_checkout}/apple_pay/payment", {"request": token}
        )

    # ── token API ──────────────────────────────────────────────────────────

    async def create_token(self, req: CreateTokenRequest) -> TokenResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/credit_cards",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            api_version="3",
        )
        return TokenResponse.model_validate(data)

    # ── gateway: card tokenization transaction ─────────────────────────────

    async def create_tokenization(
        self, req: TokenizationRequest, request_id: str | None = None
    ) -> Transaction:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/transactions/tokenizations",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            api_version="3",
            request_id=request_id,
        )
        return Transaction.model_validate(data["transaction"])

    async def masterpass_login(
        self, req: MasterpassLoginRequest
    ) -> MasterpassLoginResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/masterpass/login",
            req.model_dump(by_alias=True, exclude_none=True),
            api_version="3",
        )
        return MasterpassLoginResponse.model_validate(data)

    async def masterpass_get_cards(
        self, req: MasterpassGetCardsRequest
    ) -> MasterpassGetCardsResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/masterpass/get_cards",
            req.model_dump(by_alias=True, exclude_none=True),
            api_version="3",
        )
        return MasterpassGetCardsResponse.model_validate(data)

    async def masterpass_get_card(
        self, req: MasterpassGetCardRequest
    ) -> MasterpassCardResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/masterpass/get_card",
            req.model_dump(by_alias=True, exclude_none=True),
            api_version="3",
        )
        return MasterpassCardResponse.model_validate(data)

    async def masterpass_get_saved_card(
        self, req: MasterpassGetSavedCardRequest
    ) -> MasterpassCardResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/masterpass/get_saved_card",
            req.model_dump(by_alias=True, exclude_none=True),
            api_version="3",
        )
        return MasterpassCardResponse.model_validate(data)

    async def masterpass_delete_card(
        self, req: MasterpassDeleteCardRequest
    ) -> MasterpassDeleteCardResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/masterpass/delete_card",
            req.model_dump(by_alias=True, exclude_none=True),
            api_version="3",
        )
        return MasterpassDeleteCardResponse.model_validate(data)

    # ── checkout API ───────────────────────────────────────────────────────

    async def create_checkout(self, req: CheckoutRequest) -> CheckoutResponse:
        data = await self._request(
            "POST",
            f"{self._base_checkout}/ctp/api/checkouts",
            {"checkout": req.model_dump(by_alias=True, exclude_none=True)},
            api_version="2",
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
            api_version="2",
        )

    # ── direct / APM API ───────────────────────────────────────────────────

    async def create_apm_payment(
        self, req: ApmPaymentRequest, request_id: str | None = None
    ) -> ApmPaymentResponse:
        body = req.model_dump(by_alias=True, exclude_none=True)
        body["method"] = body.pop("payment_method")
        data = await self._request(
            "POST",
            f"{self._base_api}/beyag/transactions/payments",
            {"request": body},
            request_id=request_id,
        )
        return ApmPaymentResponse.model_validate(data["transaction"])

    async def apm_refund(
        self, req: ApmRefundRequest, request_id: str | None = None
    ) -> ApmRefundResponse:
        data = await self._request(
            "POST",
            f"{self._base_api}/beyag/transactions/refunds",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            request_id=request_id,
        )
        return ApmRefundResponse.model_validate(data["transaction"])

    async def apm_full_refund(
        self,
        parent_uid: str,
        reason: str,
        amount: int | None = None,
        request_id: str | None = None,
    ) -> ApmRefundResponse:
        if amount is None:
            raise ValueError("amount is required for /beyag/refunds")
        req = ApmRefundRequest(parent_uid=parent_uid, reason=reason, amount=amount)
        data = await self._request(
            "POST",
            f"{self._base_api}/beyag/refunds",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            request_id=request_id,
        )
        return ApmRefundResponse.model_validate(data["transaction"])

    async def confirm_apm_payment(
        self, uid: str, req: ApmConfirmRequest, request_id: str | None = None
    ) -> ApmConfirmResponse:
        reference_mode = (
            req.transaction_reference is not None
            or req.skip_duplicate_check is not None
        )
        if (
            sum(value is not None for value in (req.confirm_type, req.phone))
            + reference_mode
            > 1
        ):
            raise ValueError(
                "transaction_reference/skip_duplicate_check, confirm_type and phone are mutually exclusive"
            )
        if req.confirm_type is not None and req.confirm_type not in (
            "confirm",
            "cancel",
        ):
            raise ValueError("confirm_type must be confirm or cancel")
        body = req.model_dump(by_alias=True, exclude_none=True)
        data = await self._request(
            "POST",
            f"{self._base_api}/beyag/transactions/{uid}/confirm",
            {"request": body} if req.phone is None else body,
            request_id=request_id,
        )
        return ApmConfirmResponse.model_validate(
            data["transaction" if req.confirm_type is not None else "response"]
        )

    async def get_apm_transaction(self, uid: str) -> Transaction:
        data = await self._request("GET", f"{self._base_api}/beyag/transactions/{uid}")
        return Transaction.model_validate(data["transaction"])

    async def get_apm_transactions_by_tracking_id(
        self, tracking_id: str
    ) -> list[Transaction]:
        data = await self._request(
            "GET",
            f"{self._base_api}/beyag/transactions/tracking_id/{tracking_id}",
        )
        return [Transaction.model_validate(item) for item in data["transactions"]]

    async def apm_payout(
        self, req: ApmPayoutRequest, request_id: str | None = None
    ) -> ApmPayoutResponse:
        data = await self._request(
            "POST",
            f"{self._base_api}/beyag/transactions/payouts",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            request_id=request_id,
        )
        return ApmPayoutResponse.model_validate(data["transaction"])

    async def apm_proof(
        self, uid: str, req: ProofRequest, request_id: str | None = None
    ) -> ProofResponse:
        data = await self._request(
            "POST",
            f"{self._base_api}/beyag/transactions/{uid}/proof",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            request_id=request_id,
        )
        return ProofResponse.model_validate(data["transaction"])

    async def check_mts_service(
        self, phone: str, test: bool | None = None
    ) -> CheckServiceResponse:
        request = {"customer": {"phone": phone}}
        if test is not None:
            request["test"] = test
        data = await self._request(
            "POST",
            f"{self._base_api}/beyag/gateways/mts_money_widget/check_service",
            {"request": request},
            api_version="3",
        )
        return CheckServiceResponse.model_validate(data)

    async def check_mts_service_v2(
        self, phone: str, test: bool | None = None
    ) -> CheckServiceResponse:
        request: dict[str, Any] = {"customer": {"phone": phone}}
        if test is not None:
            request["test"] = test
        data = await self._request(
            "POST",
            f"{self._base_api}/beyag/gateways/mts_money/check_service",
            {"request": request},
            api_version="2",
        )
        return CheckServiceResponse.model_validate(data)

    async def test_qiwi_terminal_payment(
        self, amount: int, currency: str, account: str
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"{self._base_api}/beyag/testing/payment",
            {
                "request": {
                    "amount": amount,
                    "currency": currency,
                    "method": {"type": "qiwi_terminal", "account": account},
                    "test": True,
                }
            },
        )

    async def create_erip_payment(
        self, req: ApmPaymentRequest, request_id: str | None = None
    ) -> ApmPaymentResponse:
        if req.currency != "BYN":
            raise ValueError("currency must be BYN for ERIP")
        if not req.description or not req.ip:
            raise ValueError("description and ip are required for ERIP")
        if req.payment_method.get("type") != "erip":
            raise ValueError("payment_method.type must be erip")
        account_number = req.payment_method.get("account_number")
        if not isinstance(account_number, str) or not account_number:
            raise ValueError("payment_method.account_number must be a non-empty string")
        data = await self._request(
            "POST",
            f"{self._base_api}/beyag/payments",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            request_id=request_id,
        )
        return ApmPaymentResponse.model_validate(data["transaction"])

    async def get_apm_refund(self, uid: str) -> ApmRefundResponse:
        data = await self._request("GET", f"{self._base_api}/beyag/refunds/{uid}")
        return ApmRefundResponse.model_validate(data["transaction"])

    async def get_erip_pay_list(
        self, req: EripPayListRequest
    ) -> dict[str, Any] | list[dict[str, Any]]:
        data = await self._request(
            "POST", f"{self._base_api}/beyag/gateways/komplat/get_pay_list", req
        )
        return TypeAdapter(dict[str, Any] | list[dict[str, Any]]).validate_python(data)

    async def get_erip_payment(self, uid: str) -> Transaction:
        data = await self._request("GET", f"{self._base_api}/beyag/payments/{uid}")
        return Transaction.model_validate(data["transaction"])

    async def get_erip_payment_by_order_id(self, order_id: str) -> Transaction:
        data = await self._request(
            "GET", f"{self._base_api}/beyag/payments/?order_id={order_id}"
        )
        return Transaction.model_validate(data["transaction"])

    async def delete_erip_payment(self, uid: str) -> Transaction:
        data = await self._request("DELETE", f"{self._base_api}/beyag/payments/{uid}")
        return Transaction.model_validate(data["transaction"])

    async def checkup(
        self, req: CheckupRequest, request_id: str | None = None
    ) -> Transaction:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/transactions/checkups",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            api_version="3",
            request_id=request_id,
        )
        return Transaction.model_validate(data["transaction"])

    # ── P2P transfer ───────────────────────────────────────────────────────

    async def create_p2p(self, req: P2pRequest) -> P2pResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/transactions/p2ps",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            api_version="3",
        )
        return P2pResponse.model_validate(data["transaction"])

    async def verify_p2p(self, req: P2pRequest) -> VerifyP2pResponse:
        """Check whether a P2P transfer is possible and get commission details.

        Response is flat (no transaction envelope).
        """
        data = await self._request(
            "POST",
            f"{self._base_gateway}/p2p-restrictions",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
        )
        return VerifyP2pResponse.model_validate(data)

    async def verify_visa_alias(
        self, req: VisaAliasPhoneRequest
    ) -> VisaAliasPhoneResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/services/visa-alias/verify-phone",
            req,
            api_version="3",
        )
        return VisaAliasPhoneResponse.model_validate(data)

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

    async def create_payout(
        self, req: PayoutRequest, request_id: str | None = None
    ) -> PayoutResponse:
        data = await self._request(
            "POST",
            f"{self._base_gateway}/transactions/payouts",
            {"request": req.model_dump(by_alias=True, exclude_none=True)},
            api_version="3",
            request_id=request_id,
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

    # ── APM currency query ───────────────────────────────────────────────────

    async def get_currencies(self, req: CurrencyQueryRequest) -> CurrencyInfo:
        data = await self._request(
            "POST",
            f"{self._base_api}/beyag/currencies",
            req.model_dump(by_alias=True, exclude_none=True),
        )
        return CurrencyInfo.model_validate(data)

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

    All calls share a single persistent event loop and one http client, so
    connections are reused across calls. Call :meth:`close` to release them,
    or use it as a context manager. Not thread-safe: use one client per thread.
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
        self._loop: asyncio.AbstractEventLoop | None = None
        self._async: AsyncBepaidClient | None = None

    def _client(self) -> AsyncBepaidClient:
        if self._async is None:
            self._async = AsyncBepaidClient(
                self._shop_id,
                self._secret_key,
                timeout=self._timeout,
                base_gateway_url=self._base_gateway,
                base_checkout_url=self._base_checkout,
                base_api_url=self._base_api,
                base_merchant_url=self._base_merchant,
                transport=self._transport,
            )
        return self._async

    def _run(self, coro: Coroutine[Any, Any, T]) -> T:
        loop = self._loop
        if loop is None or loop.is_closed():
            loop = self._loop = asyncio.new_event_loop()
        return loop.run_until_complete(coro)

    async def _call(self, operation: str, *args: object) -> Any:
        return await getattr(self._client(), operation)(*args)

    def _invoke(self, operation: str, *args: object) -> Any:
        return self._run(self._call(operation, *args))

    def close(self) -> None:
        if self._loop is None:
            return
        if self._async is not None:
            self._loop.run_until_complete(self._async.aclose())
        self._loop.close()
        self._loop = None
        self._async = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── gateway API ────────────────────────────────────────────────────────

    def create_payment(
        self, req: PaymentRequest, request_id: str | None = None
    ) -> Transaction:
        return self._invoke("create_payment", req, request_id)

    def create_authorization(
        self, req: AuthorizationRequest, request_id: str | None = None
    ) -> Transaction:
        return self._invoke("create_authorization", req, request_id)

    def create_payment_async(
        self, req: PaymentRequest, request_id: str | None = None
    ) -> AsyncAck:
        return self._invoke("create_payment_async", req, request_id)

    def create_authorization_async(
        self, req: AuthorizationRequest, request_id: str | None = None
    ) -> AsyncAck:
        return self._invoke("create_authorization_async", req, request_id)

    def get_async_status(self, url: str) -> AsyncStatus:
        return self._invoke("get_async_status", url)

    def get_async_result(self, url: str) -> Transaction:
        return self._invoke("get_async_result", url)

    def get_card_balance(self, req: CardBalanceRequest) -> CardBalanceResponse:
        return self._invoke("get_card_balance", req)

    def capture(
        self, req: CaptureRequest, request_id: str | None = None
    ) -> CaptureResponse:
        return self._invoke("capture", req, request_id)

    def void(self, req: VoidRequest, request_id: str | None = None) -> VoidResponse:
        return self._invoke("void", req, request_id)

    def refund(
        self, req: RefundRequest, request_id: str | None = None
    ) -> RefundResponse:
        return self._invoke("refund", req, request_id)

    def get_transaction(self, uid: str) -> Transaction:
        return self._invoke("get_transaction", uid)

    def get_transaction_by_tracking_id(self, tracking_id: str) -> TrackingIdStatus:
        return self._invoke("get_transaction_by_tracking_id", tracking_id)

    # ── saved-card charges ─────────────────────────────────────────────────

    def charge_saved_card(
        self, req: ChargeRequest, request_id: str | None = None
    ) -> Transaction:
        return self._invoke("charge_saved_card", req, request_id)

    # ── recipient tokenization ─────────────────────────────────────────────

    def tokenize_recipient_card(
        self, req: RecipientTokenizationRequest
    ) -> dict[str, Any]:
        return self._invoke("tokenize_recipient_card", req)

    # ── Apple Pay ──────────────────────────────────────────────────────────

    def apple_pay_payment(self, token: str) -> dict[str, Any]:
        return self._invoke("apple_pay_payment", token)

    # ── token API ──────────────────────────────────────────────────────────

    def create_token(self, req: CreateTokenRequest) -> TokenResponse:
        return self._invoke("create_token", req)

    def create_tokenization(
        self, req: TokenizationRequest, request_id: str | None = None
    ) -> Transaction:
        return self._invoke("create_tokenization", req, request_id)

    def masterpass_login(self, req: MasterpassLoginRequest) -> MasterpassLoginResponse:
        return self._invoke("masterpass_login", req)

    def masterpass_get_cards(
        self, req: MasterpassGetCardsRequest
    ) -> MasterpassGetCardsResponse:
        return self._invoke("masterpass_get_cards", req)

    def masterpass_get_card(
        self, req: MasterpassGetCardRequest
    ) -> MasterpassCardResponse:
        return self._invoke("masterpass_get_card", req)

    def masterpass_get_saved_card(
        self, req: MasterpassGetSavedCardRequest
    ) -> MasterpassCardResponse:
        return self._invoke("masterpass_get_saved_card", req)

    def masterpass_delete_card(
        self, req: MasterpassDeleteCardRequest
    ) -> MasterpassDeleteCardResponse:
        return self._invoke("masterpass_delete_card", req)

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

    def create_apm_payment(
        self, req: ApmPaymentRequest, request_id: str | None = None
    ) -> ApmPaymentResponse:
        return self._invoke("create_apm_payment", req, request_id)

    def apm_refund(
        self, req: ApmRefundRequest, request_id: str | None = None
    ) -> ApmRefundResponse:
        return self._invoke("apm_refund", req, request_id)

    def apm_full_refund(
        self,
        parent_uid: str,
        reason: str,
        amount: int | None = None,
        request_id: str | None = None,
    ) -> ApmRefundResponse:
        return self._invoke("apm_full_refund", parent_uid, reason, amount, request_id)

    def confirm_apm_payment(
        self, uid: str, req: ApmConfirmRequest, request_id: str | None = None
    ) -> ApmConfirmResponse:
        return self._invoke("confirm_apm_payment", uid, req, request_id)

    def get_apm_transaction(self, uid: str) -> Transaction:
        return self._invoke("get_apm_transaction", uid)

    def get_apm_transactions_by_tracking_id(
        self, tracking_id: str
    ) -> list[Transaction]:
        return self._invoke("get_apm_transactions_by_tracking_id", tracking_id)

    def apm_payout(
        self, req: ApmPayoutRequest, request_id: str | None = None
    ) -> ApmPayoutResponse:
        return self._invoke("apm_payout", req, request_id)

    def apm_proof(
        self, uid: str, req: ProofRequest, request_id: str | None = None
    ) -> ProofResponse:
        return self._invoke("apm_proof", uid, req, request_id)

    def check_mts_service(
        self, phone: str, *, test: bool | None = None
    ) -> CheckServiceResponse:
        return self._invoke("check_mts_service", phone, test)

    def check_mts_service_v2(
        self, phone: str, *, test: bool | None = None
    ) -> CheckServiceResponse:
        return self._invoke("check_mts_service_v2", phone, test)

    def test_qiwi_terminal_payment(
        self, amount: int, currency: str, account: str
    ) -> dict[str, Any]:
        return self._invoke("test_qiwi_terminal_payment", amount, currency, account)

    def create_erip_payment(
        self, req: ApmPaymentRequest, request_id: str | None = None
    ) -> ApmPaymentResponse:
        return self._invoke("create_erip_payment", req, request_id)

    def get_apm_refund(self, uid: str) -> ApmRefundResponse:
        return self._invoke("get_apm_refund", uid)

    def get_erip_pay_list(
        self, req: EripPayListRequest
    ) -> dict[str, Any] | list[dict[str, Any]]:
        return self._invoke("get_erip_pay_list", req)

    def get_erip_payment(self, uid: str) -> Transaction:
        return self._invoke("get_erip_payment", uid)

    def get_erip_payment_by_order_id(self, order_id: str) -> Transaction:
        return self._invoke("get_erip_payment_by_order_id", order_id)

    def delete_erip_payment(self, uid: str) -> Transaction:
        return self._invoke("delete_erip_payment", uid)

    def checkup(
        self, req: CheckupRequest, request_id: str | None = None
    ) -> Transaction:
        return self._invoke("checkup", req, request_id)

    # ── P2P transfer ───────────────────────────────────────────────────────

    def create_p2p(self, req: P2pRequest) -> P2pResponse:
        return self._invoke("create_p2p", req)

    def verify_p2p(self, req: P2pRequest) -> VerifyP2pResponse:
        return self._invoke("verify_p2p", req)

    def verify_visa_alias(self, req: VisaAliasPhoneRequest) -> VisaAliasPhoneResponse:
        return self._invoke("verify_visa_alias", req)

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

    def create_payout(
        self, req: PayoutRequest, request_id: str | None = None
    ) -> PayoutResponse:
        return self._invoke("create_payout", req, request_id)

    # ── APM balance query ───────────────────────────────────────────────────

    def get_balance(self, req: BalanceRequest) -> BalanceResponse:
        return self._invoke("get_balance", req)

    # ── APM currency query ───────────────────────────────────────────────────

    def get_currencies(self, req: CurrencyQueryRequest) -> CurrencyInfo:
        return self._invoke("get_currencies", req)

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


def _basic_auth_header(shop_id: str, secret_key: str) -> str:
    return "Basic " + base64.b64encode(f"{shop_id}:{secret_key}".encode()).decode()


def verify_webhook_auth(
    authorization_header: str, shop_id: str, secret_key: str
) -> bool:
    return authorization_header == _basic_auth_header(str(shop_id), secret_key)


def parse_webhook(body: str) -> WebhookNotification:
    """Parse a webhook payload into a typed notification."""
    return WebhookNotification.model_validate_json(body)


def parse_subscription_webhook(body: str) -> Subscription:
    """Parse a subscription-service webhook payload (``event``, e.g.
    ``created.subscription``)."""
    return Subscription.model_validate_json(body)


def parse_checkout_webhook(body: str) -> CheckoutStatus:
    """Parse a payment-widget webhook payload (flat checkout-shaped
    notification, e.g. a token-expiry notice without a ``transaction``
    envelope)."""
    return CheckoutStatus.model_validate_json(body)


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
