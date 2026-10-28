"""payment list-pending · payment mark-paid (slice 1).

Names locked to the t_c44a2968 §5 contract: payment_list_pending /
payment_mark_paid (MCP twins, underscore vs space only).
"""
import datetime

from .. import gate
from ..client import resolve_operator
from ..errors import ValidationError
from ..money import format_pounds, parse_amount, pence_to_pounds, validate_month


def _utcnow_iso():
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _masked_name(head_tenant):
    """SR6: tenant surname masked to initial + surname at the CLI surface."""
    if not isinstance(head_tenant, dict):
        return "-"
    first = str(head_tenant.get("first_name") or "").strip()
    last = str(head_tenant.get("last_name") or "").strip()
    if not last:
        return first or "-"
    if not first:
        return last
    return f"{first[0]}. {last}"


def cmd_list_pending(args, ctx):
    """payment list-pending --month YYYY-MM : tenancies in arrears for a month."""
    month = validate_month(args.month)
    client = ctx["client"]
    out = ctx["out"]

    data = client.get(
        "admin/get_all_tenancy",
        {"scenes": "rentControl", "arrears_value": month, "page_size": args.page_size},
    )
    rows = data.get("data") if isinstance(data, dict) else data
    rows = rows or []

    if rows:
        out.write(f"tenancies in arrears for {month}:\n")
        out.write(f"{'tenancy_id':<38} {'tenant':<20} {'monthly':>12} {'paid':>12} {'shortfall':>12}\n")
    for row in rows:
        tenancy_id = str(row.get("tenancy_id") or "")
        paid_pence = int(row.get("paid_amount") or 0)
        monthly_pence = int(parse_amount(str(row.get("monthly_rental") or "0")) * 100)
        shortfall_pence = monthly_pence - paid_pence
        out.write(
            f"{tenancy_id:<38} {_masked_name(row.get('headTenant')):<20} "
            f"{format_pounds(pence_to_pounds(monthly_pence)):>12} "
            f"{format_pounds(pence_to_pounds(paid_pence)):>12} "
            f"{format_pounds(pence_to_pounds(shortfall_pence)):>12}\n"
        )
    out.write(f"{len(rows)} tenancies in arrears for {month}\n")
    return 0


def cmd_mark_paid(args, ctx):
    """payment mark-paid --tenancy-id ID --month YYYY-MM --amount POUNDS.

    Validation happens before any network call. The pre-read surfaces the
    updateOrCreate overwrite risk (R1) instead of silently clobbering.
    """
    month = validate_month(args.month)
    amount = parse_amount(args.amount)
    if not args.tenancy_id:
        raise ValidationError("--tenancy-id required")
    client, audit, feishu = ctx["client"], ctx["audit"], ctx["feishu"]
    out, err = ctx["out"], ctx["err"]

    # Overwrite warning (R1): create_payment is updateOrCreate([tenancy_id, month]).
    schedule = client.get(
        "admin/payment_rent/get_all_payments", {"tenancy_id": args.tenancy_id}
    )
    existing = next(
        (r for r in (schedule or []) if str(r.get("month")) == month), None
    )
    if existing is not None:
        old = pence_to_pounds(int(existing.get("amount") or 0))
        err.write(f"warning: overwriting existing value £{old} with £{amount}\n")

    gate.enforce("payment_mark_paid", feishu,
                 {"tenancy_id": args.tenancy_id, "month": month, "amount": str(amount)})

    operator = resolve_operator(client)
    base_entry = {
        "ts": _utcnow_iso(),
        "command": "payment_mark_paid",
        "operator": operator,
        "params": {"tenancy_id": args.tenancy_id, "month": month, "amount": f"{amount}"},
    }
    try:
        # amount stays in POUNDS: the controller owns the ×100 (SR5).
        client.post(
            "admin/payment_rent/create_payment",
            data={
                "tenancy_id": args.tenancy_id,
                "month": month,
                "amount": f"{amount}",
            },
        )
    except Exception as exc:
        error_code = getattr(exc, "code", None)
        entry = dict(base_entry)
        entry["status"] = "error"
        entry["error_code"] = error_code
        entry["notify"] = feishu.notify_mutation(entry)
        audit.append(entry)
        raise

    entry = dict(base_entry)
    entry["status"] = "ok"
    entry["notify"] = feishu.notify_mutation(entry)
    line = audit.append(entry)
    out.write(f"payment recorded: tenancy={args.tenancy_id} month={month} amount=£{amount}\n")
    out.write(f"audit: {line['hash'][:16]} (feishu notify: {entry['notify']})\n")
    return 0