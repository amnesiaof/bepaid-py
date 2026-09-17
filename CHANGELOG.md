# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.0] - 2026-09-17

### Added
- Card balance query on the Gateway API: `get_card_balance` (async + sync) posting to `/balance` with `X-API-Version: 2` and a wrapped `{"request": ...}` body; new `CardBalanceRequest`, `CardBalanceResponse` and `CardBalanceResult` models (camelCase `gatewayId`/`bankInfo` per docs).
- Asynchronous processing mode (Gateway API): `create_payment_async` and `create_authorization_async` post to `/async/transactions/{payments|authorizations}` (v3) and return `AsyncAck`; `get_async_status(url)` returns `AsyncStatus` and `get_async_result(url)` returns the final `Transaction`.
- `CheckoutRequest` fields `dynamic_billing_descriptor` and `travel`; `CheckoutSettings` fields `style`, `widget_version`, `require`, `customer`.
- `CheckoutStatus` fields `merchant`, `version` (int or str), `card_info`, `job_id`, `attempts`, `iframe`, `dynamic_billing_descriptor`, `travel`; checkout echo fields are preserved via `extra="allow"`.
- `PaymentRequest` fields `expired_at` and `dynamic_billing_descriptor`; `AuthorizationRequest` fields `language`, `notification_url`, `return_url`, `expired_at`, `dynamic_billing_descriptor`.
- `ApmPaymentRequest` fields `iframe` and `verification_url`; `Customer` fields `id` and `id_number`.
- `ApmRefundResponse` fields `tracking_id`, `updated_at`, `method_type`, `receipt_url`, `smart_routing_verification`, `additional_data`.
- `ProductUpdateRequest` fields `name`, `description`, `currency`, `visible_fields`, `test`, `immortal`, `expired_at`, `return_url`, `shop_id`, `language`, `transaction_type`.
- `check_mts_service_v2` for the original MTS Money service check (API version 2), and `test_qiwi_terminal_payment` for QIWI terminal test payments, in both clients.
- Optional `Customer.gender` and `Customer.street` fields, and MTS service-check `error_code`.
- ERIP invoice creation via `create_erip_payment`, refund lookup via `get_apm_refund`, and flat ERIP tree requests via `get_erip_pay_list` in both clients; tree responses preserve bare objects and arrays.
- `AdditionalData.komplat` for ERIP tree authorization metadata.
- Visa Alias phone verification in both clients, with typed flat requests, root-level card data and token, and camelCase service information.
- P2P request description, expiry, duplicate checking, language, callback URLs, customer, billing addresses and additional metadata.
- Masterpass login, card listing, card retrieval, saved-card retrieval and deletion with typed requests/responses in both clients, flat gateway request bodies and API version 3.
- Masterpass session metadata in `AdditionalData`, alongside recurring contracts for payments and authorizations.

### Changed
- **BREAKING**: `create_payment` and `create_authorization` return the full `Transaction` model instead of the narrow `PaymentResponse`/`AuthorizationResponse` classes, which are removed. 3-D Secure data is available via `Transaction.three_d_secure_verification` (dict), card data via `Transaction.credit_card`.
- **BREAKING**: `ThreeDSecureVerification` is removed; use the raw `Transaction.three_d_secure_verification` dictionary. `apm_full_refund` now requires an explicit amount, and mixed APM confirmation modes raise `ValueError`.
- `AdditionalData` and `PayoutAdditionalData` accept unknown keys (`extra="allow"`), so `p2p{service_id,service_extension}`, `sub_brand`, `receipt_text`, `card_on_file`, `expected_bank_code`, `excluded_gateways` pass through to the API (AFT/OCT support).
- `BillingAddress` gains `birth_date` (kept in webhook transactions).

### Fixed
- `create_checkout` now sends the required `X-API-Version: 2` header.
- Universal APM confirmation (transaction_reference / skip_duplicate_check) sends a wrapped `{"request": {...}}` body as documented; empty `ApmConfirmRequest()` sends `{"request": {}}`, and `skip_duplicate_check` may be sent without `transaction_reference`. Wrapped BelVEB confirm/cancel and flat SberPay phone modes are unchanged.
- Async polling accepts only absolute URLs on the configured gateway origin, rejects userinfo and malformed/foreign destinations before HTTP, and never follows redirects, even when the underlying client enables them.
- Generic APM payment creation sends `method` while preserving public `payment_method` construction and ERIP invoice serialization.
- APM payment and transaction-status responses preserve method-specific JSON and object/string forms, including string cryptocurrency amounts.
- APM confirmation supports wrapped BelVEB confirm/cancel and flat SberPay phone requests, preserves the legacy reference flow, and rejects mixed confirmation modes.
- ERIP/APM payment and refund responses preserve documented metadata, raw ERIP details, QR codes and bank links; transactions preserve billing addresses and middle names.
- Webhooks retain ERIP/refund metadata and method-named External/APM objects; widget payment methods and order additional data retain method-specific sections.
- `create_erip_payment` validates ERIP currency and required fields without changing generic APM creation; `apm_full_refund` rejects omitted or `None` amounts before sending a request, while generic `apm_refund` remains unchanged.
- P2P responses preserve message, timestamps, language, payment method, additional data, customer, billing address, status code and ID; restriction responses preserve structured errors without changing the request envelope.
- `ApiError` preserves structured messages and errors plus `error_code`, `code` and `friendly_message`, including Visa Alias validation and card-not-found errors.
- Responses of payment, authorization, charge and tokenization calls preserve raw `additional_data`, including nested Masterpass results independently of transaction status.
- `CreditCardRaw.number` is optional, allowing token-only payments without dummy card fields; raw-card serialization is unchanged.
- `AuthorizationRequest.additional_data` accepts `AdditionalData`, including `contract`, and preserves it in request bodies.

## [0.5.12] - 2026-09-17

### Added
- `request_id` optional argument on host-to-host methods (`create_payment`, `create_authorization`, `capture`, `void`, `refund`, `charge_saved_card`, `create_payout`, `create_apm_payment`, `apm_refund`, `apm_full_refund`, `confirm_apm_payment`, `apm_payout`, `apm_proof`, `checkup`) to set the `RequestID` header and make requests idempotent (per bePaid idempotent requests docs).
- `AuthorizationRequest.verification_url` field to enable transaction verification.
- `parse_checkout_webhook()` to parse flat payment-widget webhook payloads (e.g. token-expiry notices) into `CheckoutStatus`.
- `CheckoutStatus` fields: `customer`, `finished`, `expired`, `shop`, `test`, `status`, `message`, `payment_method`.
- `CheckoutCustomerFields.hidden` array.
- `create_tokenization()` method (H2H, async + sync): tokenize a card via the `POST /transactions/tokenizations` endpoint (3-D Secure supported). New `TokenizationRequest` and `ThreeDSecureAdvanced` models; `Transaction.tokenization` dict; `CreditCardRaw.skip_three_d_secure_verification` and `force_three_d_secure_verification` fields.
- `PaymentRequest.duplicate_check` and `AuthorizationRequest.duplicate_check` fields (set `false` to allow a repeat request within 30 seconds instead of getting a `Duplicate transaction` error).
- `Transaction` now exposes the full v3 response format: `psp_settled_at`, `status_code` (int), `payment_method_type`, `parent_uid`, `reason`, `errors`, `customer`, `smart_routing_verification`, `three_d_secure_verification`, `additional_data`, `avs_cvc_verification`. `CreditCardInfo` gains `bin_8`, `issuer_country`, `issuer_name`, `product`, `token_provider`. `Customer` gains `address`, `country`, `city`, `state`, `zip`.

## [0.5.11] - 2026-09-16

### Added
- `parse_webhook()` and `parse_subscription_webhook()` to parse webhook payloads into typed models.

### Fixed
- `__version__` was stuck at `0.5.4`; now synced with `pyproject.toml`.

## [0.5.10] - 2026-09-16

### Added
- `CheckoutSettings` fields: `agreed`, `agreement_toggle`, `customer_fields`, `credit_card_fields`, `verification_url`, `auto_return`, `card_notification_url`, `save_card_toggle`, `another_card_toggle`.
- `PaymentMethod` fields: `excluded_types`, `excluded_brands`.
- `CheckoutOrder.expired_at`.
- `Customer` fields: `external_id`, `taxpayer_id`.

## [0.5.9] - 2026-09-16

### Added

- `confirm_type` field to `ApmConfirmRequest` for BelВеб-кредит
  confirm/cancel.

## [0.5.8] - 2026-09-16

### Added

- `custom_fields` support (bePaid API change of 2026-04-22): new
  `CustomField` and `CustomFields` models. `custom_fields` field added to
  `PaymentRequest`, `AuthorizationRequest`, `CheckoutOrder`,
  `ApmPaymentRequest`, `ApmPayoutRequest`, `PayoutRequest` and the response
  models `Transaction`, `ApmPaymentResponse`, `ApmPayoutResponse`,
  `PayoutResponse`.

## [0.5.7] - 2026-09-15

### Fixed

- Request bodies are now serialized as **snake_case** to match the bePaid
  API. Previously `CamelModel` applied a `to_camel` alias generator, so
  every request went out as camelCase (`trackingId`, `paymentMethod`, ...)
  while the API (Postman collection, API v3 spec, changelog) expects
  snake_case (`tracking_id`, `payment_method`, ...). The Rust SDK already
  did this; Python now sends the same wire format.
- `ApmPaymentRequest.erip()` gained an optional `erip_devices` argument to
  pass `EripDevice` list directly.

### Changed

- `CamelModel` no longer renames fields to camelCase; it keeps
  `populate_by_name=True` so camelCase input is still accepted.

## [0.5.6] - 2026-09-15

### Fixed

- `validate_apple_pay` now sends `X-API-Version: 2` as required by docs.

### Changed

- Removed redundant `Field(alias=...)` on `ApmPaymentRequest.payment_method`
  and `P2pInfo.type` (implicit from `CamelModel`).
- `Subscription.plan` changed from `dict` to `PlanItem`. Added
  `SubscriptionLastTransaction` class for `Subscription.last_transaction`
  (uid/status/message/created_at).
- `BepaidClient` (sync) now reuses a single event loop and
  `AsyncBepaidClient` across calls; connections are kept alive. Added
  `close()` and context-manager support (`with BepaidClient(...) as c`).

## [0.5.5] - 2026-09-15

### Added

- `X-Api-Version: 3` on all gateway API calls: `create_payment`,
  `create_authorization`, `capture`, `void`, `refund`, `get_transaction`,
  `create_token`, `create_payout`, `create_p2p`, `checkup` (and
  `charge_saved_card` already sent it).
- SberPay push constructor: `ApmPaymentRequest.sberpay()` with optional
  `phone`.
- APM constructors: `alfaclick()`, `webpay()`, `rccard()`, `byncard()`,
  `halva()`.
- MTS Money service check: `check_mts_service(phone, test=None)`.
- P2P restrictions check: `verify_p2p(req)` (`POST /p2p-restrictions`).
- ERIP payment endpoints: `get_erip_payment`, `get_erip_payment_by_order_id`,
  `delete_erip_payment` (only `pending`/`permanent` requirements can be
  deleted).
- `Transaction` fields: `id`, `order_id`, `expired_at`, `language`,
  `version`, `erip`.

## [0.5.4] - 2026-09-14

### Added

- APM transaction status queries: `get_apm_transaction` (by uid) and
  `get_apm_transactions_by_tracking_id`.
- APM payouts: `apm_payout` with `ApmPayoutRequest` / `ApmPayoutResponse`.
- APM payment proof: `apm_proof` with `ProofRequest` / `ProofDocument` /
  `ProofResponse`.
- Card checkup (risk management rules check): `checkup` with `CheckupRequest`.

## [0.5.3] - 2026-09-14

### Added

- ERIP and alternative payment method (APM) constructors on
  `ApmPaymentRequest`: `erip`, `mts_money`, `krok`, `qiwi_terminal`.
- `Customer.phone` and `EripDevice`.

## [0.5.2] - 2026-09-14

### Added

- Client-side encrypted card data (CSE): `PaymentRequest.encrypted_data`.
- Fiscalization support (KZT): `PaymentRequest.fiscalization` with positions
  and taxes.

## [0.5.1] - 2026-09-14

### Changed

- `PaymentRequest` gains `verification_url` and `return_url` for 3-D Secure
  handling in server-to-server (H2H) payments.

### Added

- Runnable example: `examples/h2h.py` (server-to-server card payment).

## [0.5.0] - 2026-09-14

### Added

- Split payments: `create_split_payment` (Direct API).
- Pay-by-link products: `create_product`, `list_products`, `get_product`,
  `update_product`.
- Payment token for the payment page/widget: `create_payment_token`.
- Webhook `Content-Signature` verification: `verify_webhook_signature`
  (RSA-SHA256 over the raw body, uses `cryptography`).
- Plan payment link: `get_plan_payment_link`.
- Saved-card charges: `charge_saved_card` (Gateway API).
- Recipient tokenization for payouts: `tokenize_recipient_card`.
- Apple Pay payment: `apple_pay_payment` (Checkout API).
- APM currency query: `get_currencies` (Direct API).
- Transaction status by tracking id: `get_transaction_by_tracking_id`.

## [0.4.0] - 2026-09-13

### Added

- Payout transactions: `create_payout` (Gateway API, `X-API-Version: 3`).
- APM balance query: `get_balance` (Direct API).
- Merchant reports: `get_reports`, `get_report_count`, `get_channel_balances`
  (Merchant API with configurable `base_merchant_url` and mixed
  `X-API-Version: 2/3`).
- `DEFAULT_MERCHANT_URL` constant and `base_merchant_url` parameter on both
  `AsyncBepaidClient` and `BepaidClient`.
- Runnable examples: `examples/payment.py` (card flow with 3-D Secure),
  `examples/subscriptions.py` (customer → plan → subscription).

## [0.3.0] - 2026-09-13

### Added

- Subscriptions service: `create_customer`, `get_customer`, `list_customers`,
  `create_plan`, `get_plan`, `list_plans`, `create_subscription`,
  `get_subscription`, `cancel_subscription`.
- P2P transfers: `create_p2p`.
- APM payment confirmation: `confirm_apm_payment`.

## [0.2.1] - 2026-09-13

### Fixed

- Python 3.10 import: `typing.Self` is 3.11+, use `typing_extensions.Self`
  fallback.

## [0.2.0] - 2026-09-13

### Added

- `AsyncBepaidClient`: full async implementation via `httpx.AsyncClient`.
- Sync `BepaidClient` now wraps the async implementation via `asyncio.run`.

## [0.1.0] - 2026-09-13

### Added

- Sync client (`BepaidClient`) for the bePaid API (bepaid.by) with HTTP Basic
  authentication.
- Gateway operations: `create_payment`, `create_authorization`, `capture`,
  `void`, `refund`, `get_transaction`.
- Token API: `create_token`.
- Checkout API: `create_checkout`, `get_checkout_status`,
  `validate_apple_pay`.
- Direct (APM) API: `create_apm_payment`, `apm_refund`, `apm_full_refund`.
- Webhooks: `verify_webhook_auth` and `WebhookNotification` parsing.

[Unreleased]: https://github.com/amnesiaof/bepaid-py/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/amnesiaof/bepaid-py/compare/v0.5.12...v0.6.0
[0.5.12]: https://github.com/amnesiaof/bepaid-py/compare/v0.5.11...v0.5.12
[0.5.11]: https://github.com/amnesiaof/bepaid-py/compare/v0.5.10...v0.5.11
[0.5.10]: https://github.com/amnesiaof/bepaid-py/compare/v0.5.9...v0.5.10
[0.5.9]: https://github.com/amnesiaof/bepaid-py/compare/v0.5.8...v0.5.9
[0.5.8]: https://github.com/amnesiaof/bepaid-py/compare/v0.5.7...v0.5.8
[0.5.7]: https://github.com/amnesiaof/bepaid-py/compare/v0.5.6...v0.5.7
[0.5.6]: https://github.com/amnesiaof/bepaid-py/compare/v0.5.5...v0.5.6
[0.5.5]: https://github.com/amnesiaof/bepaid-py/compare/v0.5.4...v0.5.5
[0.5.4]: https://github.com/amnesiaof/bepaid-py/compare/v0.5.3...v0.5.4
[0.5.3]: https://github.com/amnesiaof/bepaid-py/compare/v0.5.2...v0.5.3
[0.5.2]: https://github.com/amnesiaof/bepaid-py/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/amnesiaof/bepaid-py/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/amnesiaof/bepaid-py/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/amnesiaof/bepaid-py/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/amnesiaof/bepaid-py/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/amnesiaof/bepaid-py/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/amnesiaof/bepaid-py/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/amnesiaof/bepaid-py/releases/tag/v0.1.0