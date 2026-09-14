"""Server-to-server (H2H) card payment.

Unlike the customer-facing flows, H2H charges the card straight from your
back end. When 3-D Secure is mandatory the gateway returns a
three_d_secure_verification block in the transaction and the customer
must still verify.

Run with SHOP_ID and SECRET_KEY environment variables set:

    SHOP_ID=363 SECRET_KEY=secret python examples/h2h.py
"""

import os
import time

from bepaid import BepaidClient
from bepaid.models import AdditionalData, CreditCardRaw, Customer, PaymentRequest


def main() -> None:
    client = BepaidClient(os.environ["SHOP_ID"], os.environ["SECRET_KEY"])

    # 1. Charge the card server-to-server. return_url is where the customer
    #    lands after 3-D Secure; verification_url is where the 3-D Secure
    #    request posts the result.
    payment = client.create_payment(
        PaymentRequest(
            amount="700",  # minor units
            currency="USD",
            test=True,
            description="H2H test payment",
            tracking_id=f"h2h-{int(time.time() * 1000)}",
            verification_url="https://example.com/3ds-verify",
            return_url="https://example.com/payment-return",
            credit_card=CreditCardRaw(
                number="4242424242424242",
                verification_value="123",
                holder="John Smith",
                exp_month=10,
                exp_year=2030,
                save_card=True,
            ),
            customer=Customer(ip="127.0.0.1", email="john@example.com"),
            additional_data=AdditionalData(contract=["recurring"]),
        )
    )
    print(f"payment uid: {payment.uid}")

    # 2. Poll the transaction until it leaves `incomplete`. When 3-D Secure
    #    is triggered, handle three_d_secure_verification and follow the
    #    redirect before retrying.
    while True:
        tx = client.get_transaction(payment.uid)
        print(f"status: {tx.status}")
        if tx.status in ("successful", "failed"):
            break
        time.sleep(2)


if __name__ == "__main__":
    main()
