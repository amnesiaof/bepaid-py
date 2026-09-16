# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[Unreleased]: https://github.com/amnesiaof/bepaid-py/compare/v0.5.6...HEAD
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