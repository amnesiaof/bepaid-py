# bepaid

Python client for the [bePaid payment API](https://docs.bepaid.by) (bepaid.by).

Covers the Gateway API (card payments, tokenization, capture, void, refunds),
the hosted Checkout API, and the Direct/APM API (alternative payment methods).
Built on `httpx` and `pydantic`.

## Install

```bash
uv add bepaid
# or
pip install bepaid
```

Requires Python 3.10+.

## Usage

```python
from bepaid import BepaidClient
from bepaid.models import PaymentRequest, CreditCardRaw

client = BepaidClient("shop_id", "secret_key")

# amounts are strings in minor units, e.g. "700" = 7.00 BYN
payment = client.create_payment(
    PaymentRequest(
        amount="700",
        currency="BYN",
        test=True,
        description="Order #123",
        tracking_id="order-123",
        credit_card=CreditCardRaw(
            number="4242424242424242",
            verification_value="123",
            holder="John Smith",
            exp_month=10,
            exp_year=2030,
            save_card=True,
        ),
    )
)
```

### Async

`AsyncBepaidClient` mirrors the synchronous API and supports `async with`:

```python
from bepaid import AsyncBepaidClient

async with AsyncBepaidClient("shop_id", "secret_key") as client:
    payment = await client.create_payment(...)

# or without the context manager:
client = AsyncBepaidClient("shop_id", "secret_key")
try:
    payment = await client.create_payment(...)
finally:
    await client.aclose()
```

`BepaidClient` is a thin synchronous wrapper around `AsyncBepaidClient`
(each call runs on a fresh event loop, so it does not reuse connections);
prefer the async client inside an asyncio application.

### Authorization with 3-D Secure

```python
auth = client.create_authorization(AuthorizationRequest(amount=700, currency="BYN", ...))
# redirect the customer to auth.redirect_url, then poll for the result:
tx = client.get_transaction(auth.uid)
```

### Hosted checkout

```python
checkout = client.create_checkout(
    CheckoutRequest(
        transaction_type="payment",
        order=CheckoutOrder(currency="BYN", amount=700, description="Order #123"),
        settings=CheckoutSettings(
            return_url="https://example.com/return",
            notification_url="https://example.com/webhook",
        ),
    )
)
# redirect the customer to checkout.redirect_url
```

### Tokenization

```python
token = client.create_token(
    CreateTokenRequest(
        number="4200000000000000",
        holder="John Smith",
        exp_month="05",
        exp_year="2028",
        contract=["recurring"],
    )
)
# store token.token, use it later without re-entering card details
```

### APM payments (Direct API)

```python
apm = client.create_apm_payment(
    ApmPaymentRequest(
        amount=700,
        currency="BYN",
        payment_method={"type": "erip", "service_no": "0000000001"},
    )
)
```

### Webhooks

```python
from bepaid.client import verify_webhook_auth
from bepaid.models import WebhookNotification

assert verify_webhook_auth(authorization_header, shop_id, secret_key)
notification = WebhookNotification.model_validate_json(raw_body)
```

## API coverage

| Group     | Operations |
|-----------|------------|
| Gateway   | `create_payment`, `create_authorization`, `capture`, `void`, `refund`, `get_transaction` |
| Tokens    | `create_token` |
| Checkout  | `create_checkout`, `get_checkout_status`, `validate_apple_pay` |
| Direct    | `create_apm_payment`, `apm_refund`, `apm_full_refund` |
| Webhooks  | verification + payload parsing |

## License

MIT