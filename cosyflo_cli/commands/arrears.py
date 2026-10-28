"""arrears list (slice 1). Name locked to the contract: arrears_list."""
from ..errors import ValidationError
from ..money import format_pounds, pence_to_pounds


def cmd_list(args, ctx):
    """arrears list --tenancy-id ID : per-tenancy payment schedule with arrears marks."""
    if not args.tenancy_id:
        raise ValidationError("--tenancy-id required")
    client, out = ctx["client"], ctx["out"]

    rows = client.get(
        "admin/payment_rent/get_all_payments", {"tenancy_id": args.tenancy_id}
    )
    rows = rows or []

    if not rows:
        out.write(f"no payment schedule for {args.tenancy_id}\n")
        return 0

    out.write(f"payment schedule for {args.tenancy_id}:\n")
    out.write(f"{'month':<10} {'amount':>12} {'monthly':>12} {'shortfall':>12}  status\n")
    for row in sorted(rows, key=lambda r: str(r.get("month") or "")):
        month = str(row.get("month") or "-")
        amount_p = int(row.get("amount") or 0)
        monthly_p = int(row.get("monthly_rental") or 0)
        shortfall_p = monthly_p - amount_p
        status = "ARREARS" if amount_p < monthly_p else "paid"
        out.write(
            f"{month:<10} {format_pounds(pence_to_pounds(amount_p)):>12} "
            f"{format_pounds(pence_to_pounds(monthly_p)):>12} "
            f"{format_pounds(pence_to_pounds(shortfall_p)):>12}  {status}\n"
        )
    return 0