"""Pydantic models for the bePaid API (aliases use camelCase as the API expects)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class BillingAddress(CamelModel):
    first_name: str | None = None
    last_name: str | None = None
    country: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    address: str | None = None
    phone: str | None = None


class Customer(CamelModel):
    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    ip: str | None = None
    email: str | None = None
    device_id: str | None = None
    birth_date: str | None = None


class BrowserInfo(CamelModel):
    screen_width: int | None = None
    screen_height: int | None = None
    screen_color_depth: int | None = None
    language: str | None = None
    java_enabled: bool | None = None
    user_agent: str | None = None
    time_zone: int | None = None
    time_zone_name: str | None = None
    accept_header: str | None = None
    window_height: int | None = None
    window_width: int | None = None


class AdditionalData(CamelModel):
    browser: BrowserInfo | None = None
    contract: list[str] | None = None
    referer: str | None = None


class CreditCardRaw(CamelModel):
    number: str
    verification_value: str | None = None
    holder: str | None = None
    exp_month: int | None = None
    exp_year: int | None = None
    save_card: bool | None = None
    token: str | None = None


class CreditCardInfo(CamelModel):
    holder: str | None = None
    stamp: str | None = None
    brand: str | None = None
    last_4: str | None = None
    first_1: str | None = None
    bin: str | None = None
    exp_month: int | None = None
    exp_year: int | None = None
    token: str | None = None


class PaymentInfo(CamelModel):
    auth_code: str | None = None
    bank_code: str | None = None
    rrn: str | None = None
    ref_id: str | None = None
    message: str | None = None
    amount: int | None = None
    currency: str | None = None
    billing_descriptor: str | None = None
    gateway_id: int | None = None
    status: str | None = None


class ThreeDSecureVerification(CamelModel):
    status: str | None = None
    message: str | None = None
    pa_res_url: str | None = None
    eci: str | None = None


# ── gateway ───────────────────────────────────────────────────────────────────


class PaymentRequest(CamelModel):
    amount: str
    currency: str
    test: bool
    description: str
    tracking_id: str
    language: str | None = None
    notification_url: str | None = None
    billing_address: BillingAddress | None = None
    credit_card: CreditCardRaw | None = None
    customer: Customer | None = None
    additional_data: AdditionalData | None = None


class PaymentResponse(CamelModel):
    tracking_id: str | None = None
    uid: str


class AuthorizationRequest(CamelModel):
    amount: int
    currency: str
    description: str
    tracking_id: str
    payment_method_type: str | None = None
    test: bool | None = None
    credit_card: CreditCardRaw | None = None
    customer: Customer | None = None
    billing_address: BillingAddress | None = None


class AuthorizationResponse(CamelModel):
    uid: str
    status: str | None = None
    redirect_url: str | None = None
    three_d_secure_verification: ThreeDSecureVerification | None = None


class Transaction(CamelModel):
    uid: str
    status: str | None = None
    amount: int | None = None
    currency: str | None = None
    description: str | None = None
    tracking_id: str | None = None
    message: str | None = None
    type: str | None = None
    test: bool | None = None
    payment: PaymentInfo | None = None
    credit_card: CreditCardInfo | None = None
    code: str | None = None
    friendly_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    paid_at: str | None = None
    receipt_url: str | None = None
    redirect_url: str | None = None


class CaptureRequest(CamelModel):
    parent_uid: str
    amount: int
    tracking_id: str | None = None
    additional_data: AdditionalData | None = None


class CaptureResponse(CamelModel):
    uid: str
    status: str | None = None
    type: str | None = None
    parent_uid: str | None = None
    amount: int | None = None
    currency: str | None = None
    code: str | None = None


class VoidRequest(CamelModel):
    parent_uid: str
    amount: int
    tracking_id: str | None = None
    additional_data: AdditionalData | None = None


class VoidResponse(CamelModel):
    uid: str
    status: str | None = None
    type: str | None = None
    message: str | None = None
    code: str | None = None
    tracking_id: str | None = None
    receipt_url: str | None = None


class RefundRequest(CamelModel):
    parent_uid: str
    amount: int
    reason: str
    tracking_id: str | None = None
    additional_data: AdditionalData | None = None


class RefundResponse(CamelModel):
    uid: str | None = None
    parent_uid: str | None = None
    type: str | None = None
    status: str | None = None
    message: str | None = None
    amount: int | None = None
    currency: str | None = None
    created_at: str | None = None
    reason: str | None = None
    refund: dict[str, Any] | None = None


# ── token API ─────────────────────────────────────────────────────────────────


class CreateTokenRequest(CamelModel):
    number: str
    holder: str
    exp_month: str
    exp_year: str
    contract: list[str] | None = None


class TokenResponse(CamelModel):
    holder: str | None = None
    stamp: str | None = None
    brand: str | None = None
    last_4: str | None = None
    first_1: str | None = None
    token: str | None = None
    exp_month: int | None = None
    exp_year: int | None = None


# ── checkout API ──────────────────────────────────────────────────────────────


class CheckoutSettings(CamelModel):
    return_url: str | None = None
    success_url: str | None = None
    decline_url: str | None = None
    fail_url: str | None = None
    cancel_url: str | None = None
    notification_url: str | None = None
    button_next_text: str | None = None
    auto_pay: bool | None = None
    language: str | None = None


class PaymentMethod(CamelModel):
    types: list[str] | None = None


class CheckoutCreditCard(CamelModel):
    token: str | None = None


class CheckoutOrder(CamelModel):
    currency: str
    amount: int
    description: str | None = None
    tracking_id: str | None = None


class CheckoutRequest(CamelModel):
    test: bool | None = None
    transaction_type: str = "payment"
    attempts: int | None = None
    iframe: bool | None = None
    settings: CheckoutSettings | None = None
    payment_method: PaymentMethod | None = None
    credit_card: CheckoutCreditCard | None = None
    order: CheckoutOrder
    customer: Customer | None = None


class CheckoutResponse(CamelModel):
    token: str
    redirect_url: str | None = None


class CheckoutStatus(CamelModel):
    token: str | None = None
    shop_id: int | None = None
    transaction_type: str | None = None
    gateway_response: dict[str, Any] | None = None
    order: dict[str, Any] | None = None
    settings: CheckoutSettings | None = None


# ── direct / APM API ──────────────────────────────────────────────────────────


class ApmPaymentRequest(CamelModel):
    amount: int
    currency: str
    description: str | None = None
    email: str | None = None
    ip: str | None = None
    success_url: str | None = None
    order_id: str | int | None = None
    tracking_id: str | None = None
    notification_url: str | None = None
    expired_at: str | None = None
    test: bool | None = None
    language: str | None = None
    return_url: str | None = None
    customer: Customer | None = None
    payment_method: dict[str, Any] = Field(alias="paymentMethod")
    additional_data: dict[str, Any] | None = None


class ApmPaymentResponse(CamelModel):
    uid: str | None = None
    status: str | None = None
    type: str | None = None
    amount: int | None = None
    currency: str | None = None
    message: str | None = None
    tracking_id: str | None = None
    test: bool | None = None
    method_type: str | None = None
    receipt_url: str | None = None
    payment: PaymentInfo | None = None
    created_at: str | None = None


class ApmRefundRequest(CamelModel):
    parent_uid: str
    reason: str
    amount: int | None = None
    tracking_id: str | None = None
    additional_data: dict[str, Any] | None = None


class ApmRefundResponse(CamelModel):
    uid: str | None = None
    parent_uid: str | None = None
    type: str | None = None
    status: str | None = None
    message: str | None = None
    amount: int | None = None
    currency: str | None = None
    refund: dict[str, Any] | None = None


class ApmConfirmRequest(CamelModel):
    skip_duplicate_check: bool | None = None
    transaction_reference: str


class ApmConfirmResponse(CamelModel):
    parent_uid: str | None = None
    type: str | None = None
    status: str | None = None
    message: str | None = None
    created_at: str | None = None
    amount: int | None = None
    currency: str | None = None


# ── P2P transfer ──────────────────────────────────────────────────────────────


class P2pCard(CamelModel):
    number: str | None = None
    holder: str | None = None
    verification_value: str | None = None
    exp_month: str | None = None
    exp_year: str | None = None
    token: str | None = None


class P2pInfo(CamelModel):
    type: str | None = Field(default=None, alias="type")


class P2pAdditionalData(CamelModel):
    p2p: P2pInfo | None = None


class P2pRequest(CamelModel):
    amount: int
    currency: str
    credit_card: P2pCard
    recipient_card: P2pCard
    test: bool | None = None
    tracking_id: str | None = None
    additional_data: P2pAdditionalData | None = None


class P2pResponse(CamelModel):
    uid: str | None = None
    status: str | None = None
    amount: int | None = None
    currency: str | None = None
    description: str | None = None
    type: str | None = None
    tracking_id: str | None = None
    test: bool | None = None
    created_at: str | None = None
    redirect_url: str | None = None
    credit_card: CreditCardInfo | None = None
    recipient_card: CreditCardInfo | None = None
    receipt_url: str | None = None
    verify_p2p: dict[str, Any] | None = None
    p2p: dict[str, Any] | None = None
    sender_billing_address: BillingAddress | None = None
    recipient_billing_address: BillingAddress | None = None


# ── subscriptions API (api.bepaid.by) ────────────────────────────────────────


class CustomerRecord(CamelModel):
    id: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = None
    zip: str | None = None
    state: str | None = None
    phone: str | None = None
    email: str | None = None
    ip: str | None = None
    external_id: str | None = None


class PlanInterval(CamelModel):
    amount: int | None = None
    interval: int | None = None
    interval_unit: str | None = None
    visible_fields: list[str] | None = None


class PlanTrial(CamelModel):
    amount: int | None = None
    interval: int | None = None
    interval_unit: str | None = None
    as_first_payment: bool | None = None


class PlanItem(CamelModel):
    id: str | None = None
    test: bool | None = None
    title: str | None = None
    currency: str | None = None
    language: str | None = None
    plan: PlanInterval | None = None
    trial: PlanTrial | None = None
    infinite: bool | None = None
    billing_cycles: int | None = None
    number_payment_attempts: int | None = None
    prevent_payments_at_night: bool | None = None
    created_at: str | None = None
    updated_at: str | None = None
    pay_url: str | None = None


class SubscriptionCard(CamelModel):
    token: str | None = None
    number: str | None = None
    holder: str | None = None
    verification_value: str | None = None
    exp_month: str | None = None
    exp_year: str | None = None


class SubscriptionCustomer(CamelModel):
    id: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None


class SubscriptionPlan(CamelModel):
    id: str | None = None
    title: str | None = None
    currency: str | None = None
    plan: PlanInterval | None = None
    trial: PlanTrial | None = None


class SubscriptionCreateRequest(CamelModel):
    card: SubscriptionCard | None = None
    customer: SubscriptionCustomer | None = None
    plan: SubscriptionPlan
    tracking_id: str | None = None
    device_id: str | None = None
    return_url: str | None = None
    notification_url: str | None = None
    dynamic_billing_descriptor: str | None = None
    additional_data: dict[str, Any] | None = None
    settings: dict[str, Any] | None = None


class Subscription(CamelModel):
    id: str | None = None
    state: str | None = None
    tracking_id: str | None = None
    device_id: str | None = None
    created_at: str | None = None
    renew_at: str | None = None
    active_to: str | None = None
    card: CreditCardInfo | None = None
    customer: SubscriptionCustomer | None = None
    plan: dict[str, Any] | None = None
    last_transaction: dict[str, Any] | None = None
    paid_billing_cycles: int | None = None
    number_failed_payment_attempts: int | None = None
    additional_data: dict[str, Any] | None = None
    redirect_url: str | None = None
    event: str | None = None


class CancelSubscriptionRequest(CamelModel):
    cancel_reason: str


# ── webhook ───────────────────────────────────────────────────────────────────


class WebhookNotification(CamelModel):
    transaction: WebhookTransaction


class WebhookTransaction(CamelModel):
    uid: str
    status: str
    type: str | None = None
    amount: int | None = None
    currency: str | None = None
    description: str | None = None
    created_at: str | None = None
    method_type: str | None = None
    payment: PaymentInfo | None = None
    message: str | None = None
    tracking_id: str | None = None
    test: bool | None = None


# ── payout ────────────────────────────────────────────────────────────────────

# Payout/billing request objects must serialize with snake_case keys (the docs
# use snake_case here), so they subclass BaseModel rather than CamelModel.


class PayoutDocument(BaseModel):
    type: str | None = None
    issuer: str | None = None
    series: str | None = None
    number: str | None = None
    issued_at: str | None = None
    valid_until: str | None = None


class PayoutAdditionalData(BaseModel):
    document: PayoutDocument | None = None


class PayoutCreditCard(BaseModel):
    number: str | None = None
    holder: str | None = None
    exp_month: str | None = None
    exp_year: str | None = None


class PayoutCustomer(BaseModel):
    ip: str | None = None
    email: str | None = None
    birth_date: str | None = None


class PayoutAddress(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    country: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    address: str | None = None
    phone: str | None = None


class PayoutRequest(BaseModel):
    test: bool | None = None
    amount: int
    currency: str
    description: str | None = None
    tracking_id: str | None = None
    recipient: PayoutCustomer
    sender: PayoutCustomer
    recipient_billing_address: PayoutAddress
    sender_billing_address: PayoutAddress
    recipient_credit_card: PayoutCreditCard | None = None
    additional_data: PayoutAdditionalData | None = None


class Payout(CamelModel):
    status: str | None = None
    gateway_id: int | None = None
    ref_id: str | None = None
    bank_code: str | None = None
    rrn: str | None = None


class PayoutResponse(CamelModel):
    uid: str | None = None
    type: str | None = None
    status: str | None = None
    amount: int | None = None
    currency: str | None = None
    description: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    method_type: str | None = None
    receipt_url: str | None = None
    message: str | None = None
    tracking_id: str | None = None
    test: bool | None = None
    payout: Payout | None = None
    customer: Customer | None = None
    billing_address: BillingAddress | None = None


# ── APM balance query ─────────────────────────────────────────────────────────


class BalanceRequest(BaseModel):
    gateway_id: int
    account: str | None = None
    currency: str | None = None


class BalanceResponse(CamelModel):
    code: str | None = None
    status: str | None = None
    message: str | None = None
    friendly_message: str | None = None
    gateway_id: int | None = None
    account: str | None = None
    amount: int | None = None
    currency: str | None = None
    provider_info: dict[str, Any] | None = None


# ── merchant reports ──────────────────────────────────────────────────────────


class ReportParams(BaseModel):
    date_type: str
    date: str
    status: str
    payment_method_type: str
    time_zone: str


class ReportCountParams(BaseModel):
    date_type: str
    from_: str = Field(serialization_alias="from")
    to: str
    status: str
    payment_method_type: str
    time_zone: str


class ReportTransaction(CamelModel):
    id: int | None = None
    uid: str | None = None
    type: str | None = None
    payment_method_type: str | None = None
    status: str | None = None
    message: str | None = None
    amount: int | None = None
    discount_rate: float | None = None
    transaction_rate: float | None = None
    transaction_fee: float | None = None
    pay_to_merchant: float | None = None
    test: bool | None = None
    currency: str | None = None
    description: str | None = None
    tracking_id: str | None = None
    order_id: int | None = None
    created_at: str | None = None
    paid_at: str | None = None
    settled_at: str | None = None
    manually_corrected_at: str | None = None
    billing_address: BillingAddress | None = None
    customer: Customer | None = None
    credit_card: dict[str, Any] | None = None
    payment: dict[str, Any] | None = None
    three_d_secure_verification: dict[str, Any] | None = None
    additional_data: dict[str, Any] | None = None


class ReportListRequest(BaseModel):
    report_params: ReportParams


class ReportListResponse(CamelModel):
    transactions: list[ReportTransaction]
    count: int | None = None


class ReportCountRequest(BaseModel):
    report_params: ReportCountParams


class ReportCountResult(CamelModel):
    count: int


class ReportCountResponse(CamelModel):
    transactions: ReportCountResult


class ChannelBalance(CamelModel):
    gateway_id: int | None = None
    currency: str | None = None
    amount: int | None = None


# ── split payments ─────────────────────────────────────────────────────────────


class SplitCreditCard(BaseModel):
    token: str


class SplitAdditionalData(BaseModel):
    contract: str | None = None
    split: dict[str, int]


class SplitPaymentRequest(BaseModel):
    amount: int
    currency: str
    description: str
    tracking_id: str
    billing_address: BillingAddress | None = None
    credit_card: SplitCreditCard
    customer: Customer | None = None
    additional_data: SplitAdditionalData | None = None


class SplitItem(CamelModel):
    uid: str | None = None
    amount: int | None = None
    status: str | None = None
    message: str | None = None
    shop_id: int | None = None
    parent: bool | None = None
    parent_uid: str | None = None


class SplitPaymentResponse(CamelModel):
    splits: list[SplitItem]


WebhookNotification.model_rebuild()
