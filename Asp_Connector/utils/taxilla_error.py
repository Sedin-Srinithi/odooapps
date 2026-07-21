def humanize_taxilla_error(result: dict) -> list:
    errors = []

    try:
        # Taxilla validation response
        if result.get("detail"):
            errors.append(result["detail"])

        # Case 1 — message is a dict with response inside
        elif isinstance(result.get("message"), dict):
            inner = result["message"]
            resp = inner.get("response", {})

            if resp.get("errorDetails"):
                errors.append(resp["errorDetails"])
            elif resp.get("message"):
                errors.append(resp["message"])
            elif inner.get("message"):
                errors.append(inner["message"])

        # Case 2 — response directly present
        elif isinstance(result.get("response"), dict):
            resp = result["response"]

            if resp.get("errorDetails"):
                errors.append(resp["errorDetails"])
            elif resp.get("message"):
                errors.append(resp["message"])

        # Case 3 — plain string message
        elif isinstance(result.get("message"), str):
            errors.append(result["message"])

        errors = [
            str(e).strip()
            for e in errors
            if e and str(e).strip()
        ]

    except Exception as e:
        errors.append(f"Error parsing response: {e}")

    if not errors:
        errors.append("Unknown error from Taxilla")

    return errors