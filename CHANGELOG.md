# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/amnesiaof/bepaid-py/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/amnesiaof/bepaid-py/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/amnesiaof/bepaid-py/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/amnesiaof/bepaid-py/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/amnesiaof/bepaid-py/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/amnesiaof/bepaid-py/releases/tag/v0.1.0