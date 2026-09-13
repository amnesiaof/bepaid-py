"""Recurring subscription flow: customer -> plan -> subscription.

Run with SHOP_ID and SECRET_KEY environment variables set:

    SHOP_ID=363 SECRET_KEY=secret python examples/subscriptions.py
"""

import os

from bepaid import BepaidClient
from bepaid.models import (
    CustomerRecord,
    PlanInterval,
    PlanItem,
    SubscriptionCreateRequest,
    SubscriptionCustomer,
    SubscriptionPlan,
)


def main() -> None:
    client = BepaidClient(os.environ["SHOP_ID"], os.environ["SECRET_KEY"])

    # 1. Create a customer (or pass an existing `id` to the subscription).
    customer = client.create_customer(
        CustomerRecord(
            first_name="John",
            last_name="Smith",
            email="john@example.com",
            ip="127.0.0.1",
        )
    )
    print(f"customer: {customer.id}")

    # 2. Create a plan (or pass an existing `id` to the subscription).
    plan = client.create_plan(
        PlanItem(
            test=True,
            title="Premium",
            currency="EUR",
            plan=PlanInterval(amount=990, interval=1, interval_unit="month"),
            infinite=True,
        )
    )
    print(f"plan: {plan.title}")

    # 3. Create the subscription. For the hosted flow leave card/customer unset
    #    and a redirect_url on the response is returned.
    subscription = client.create_subscription(
        SubscriptionCreateRequest(
            customer=SubscriptionCustomer(id=customer.id),
            plan=SubscriptionPlan(id=plan.id),
            tracking_id="sub-1",
            return_url="https://example.com/return",
            notification_url="https://example.com/webhook",
        )
    )

    if subscription.redirect_url:
        print(f"3-D Secure required, redirect customer: {subscription.redirect_url}")
    print(f"subscription: {subscription.id} ({subscription.state})")


if __name__ == "__main__":
    main()
