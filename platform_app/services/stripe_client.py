import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _post_form(url, api_key, form_data):
    payload = urlencode(form_data).encode("utf-8")
    req = Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body or "{}")


def create_checkout_session(
    *,
    api_key,
    price_id,
    tenant_slug,
    customer_email,
    success_url,
    cancel_url,
):
    form_data = {
        "mode": "subscription",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": 1,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "customer_email": customer_email,
        "metadata[tenant]": tenant_slug,
    }
    return _post_form("https://api.stripe.com/v1/checkout/sessions", api_key, form_data)


def create_billing_portal_session(*, api_key, customer_id, return_url):
    form_data = {
        "customer": customer_id,
        "return_url": return_url,
    }
    return _post_form("https://api.stripe.com/v1/billing_portal/sessions", api_key, form_data)
