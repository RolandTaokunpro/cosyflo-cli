"""message draft (slice 1). Draft-only by design (SR7): renders a local template,
performs no REST call, sends nothing. No MCP twin (per spec §5 note).
"""
import os
import string

from ..errors import ValidationError

DEFAULT_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")

VALUES = ("tenant_name", "tenancy_id", "month", "amount_short")


def _template_dir(args, ctx):
    directory = args.templates_dir or ctx["config"].get("templates_dir")
    if directory:
        return directory
    return os.path.normpath(os.path.expanduser(str(DEFAULT_TEMPLATES_DIR)))


def cmd_draft(args, ctx):
    """message draft --template NAME [--tenancy-id ID --month M --tenant-name X
    --amount-short V] [--output FILE] : render a chase draft locally. Never sends."""
    directory = _template_dir(args, ctx)
    path = os.path.join(directory, f"{args.template}.txt")
    if not os.path.exists(path):
        raise ValidationError(f"unknown template {args.template}")

    with open(path) as f:
        template = f.read()

    placeholders = {
        field_name
        for _, field_name, _, _ in string.Formatter().parse(template)
        if field_name
    }
    supplied = {
        name: getattr(args, name)
        for name in VALUES
        if getattr(args, name, None) is not None
    }
    missing = sorted(p for p in placeholders if p not in supplied)
    if missing:
        raise ValidationError(
            "missing value for placeholder(s): " + ", ".join(missing)
        )

    rendered = template.format(**{p: supplied[p] for p in placeholders})

    if args.output:
        with open(args.output, "w") as f:
            f.write(rendered)
        ctx["out"].write(f"draft written to {args.output}\n")
    else:
        ctx["out"].write(rendered)
    return 0