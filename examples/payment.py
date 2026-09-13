"""Card payment flow with 3-D Secure handling.

Run with SHOP_ID and SECRET_KEY environment variables set:

    SHOP_ID=363 SECRET_KEY=secret python examples/payment.py
"""

import os

from bepaid import BepaidClient
from bepaid.models import AuthorizationRequest, CreditCardRaw, Customer


def main() -> None:
    client = BepaidClient(os.environ["SHOP_ID"], os.environ["SECRET_KEY"])

    # 1. Create an authorization: the gateway returns a redirect_url when 3-D
    #    Secure is required for the card.
    auth = client.create_authorization(
        AuthorizationRequest(
            amount=104,  # minor units
            currency="EUR",
            description="Test order",
            tracking_id="order-1",
            test=True,
            credit_card=CreditCardRaw(
                number="4242424242424242",
                verification_value="123",
                holder="John Smith",
                exp_month=10,
                exp_year=2030,
                save_card=True,
            ),
            customer=Customer(ip="127.0.0.1", email="john@example.com"),
        )
    )

    if auth.redirect_url:
        # 2. Send the customer to the URL, then poll the transaction status
        #    until it leaves the `incomplete` state.
        print(f"3-D Secure required: {auth.redirect_url}")
        print(f"uid: {auth.uid}")
    else:
        # Card did not require 3-D Secure; the authorization is complete.
        tx = client.get_transaction(auth.uid)
        print(f"authorized: {tx.status}")


if __name__ == "__main__":
    main()
