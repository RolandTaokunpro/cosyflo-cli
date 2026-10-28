"""cosyflo CLI entry point (slice 1 — payments).

Uniform per-command shape (spec §3): parse+validate -> resolve auth -> gate ->
one REST call -> audit. Exit codes: 0 success · 1 validation · 2 auth ·
3 approval denied/blocked · 4 upstream error · 5 unexpected.
"""
import argparse
import sys

import requests

from .audit import AuditLog
from .auth import fetch_token
from .client import CosyfloClient
from .commands.arrears import cmd_list
from .commands.message import cmd_draft
from .commands.payment import cmd_list_pending, cmd_mark_paid
from .config import load_config
from .errors import CliError
from .feishu import Feishu


def build_parser():
    # SUPPRESS defaults: without them the subparsers' defaults would clobber
    # values parsed at the top level (`cosyflo --config X payment ...`).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=argparse.SUPPRESS,
                        help="path to config JSON (default ~/.cosyflo-cli/config.json)")
    common.add_argument("--endpoint", default=argparse.SUPPRESS,
                        help="override the API base URL")
    common.add_argument("--token-source", choices=["op", "env"], default=argparse.SUPPRESS,
                        help="credential source override (op: 1Password via `op read`; "
                             "env: COSYFLO_API_TOKEN — dev/staging only)")

    parser = argparse.ArgumentParser(
        prog="cosyflo",
        parents=[common],
        description="Thin command layer over the Cosyflo Laravel REST API (payments slice)",
    )

    group = parser.add_subparsers(dest="group", required=True)

    payment = group.add_parser("payment", help="rent payments")
    payment_verbs = payment.add_subparsers(dest="verb", required=True)

    p_list = payment_verbs.add_parser(
        "list-pending", parents=[common], help="tenancies in arrears for a month"
    )
    p_list.add_argument("--month", required=True, help="month YYYY-MM")
    p_list.add_argument("--page-size", type=int, default=1000,
                         help="server page size (default 1000 — one call, full result)")
    p_list.set_defaults(func=cmd_list_pending, needs_auth=True)

    p_mark = payment_verbs.add_parser(
        "mark-paid", parents=[common], help="record a rent payment"
    )
    p_mark.add_argument("--tenancy-id", required=False, help="tenancy id")
    p_mark.add_argument("--month", required=True, help="month YYYY-MM")
    p_mark.add_argument("--amount", required=True,
                        help="amount in POUNDS, >= 0, max 2 decimal places")
    p_mark.set_defaults(func=cmd_mark_paid, needs_auth=True)

    arrears = group.add_parser("arrears", help="arrears schedule")
    arrears_verbs = arrears.add_subparsers(dest="verb", required=True)
    a_list = arrears_verbs.add_parser(
        "list", parents=[common], help="per-tenancy payment schedule"
    )
    a_list.add_argument("--tenancy-id", required=False, help="tenancy id")
    a_list.set_defaults(func=cmd_list, needs_auth=True)

    message = group.add_parser("message", help="chase message drafts (local render only)")
    message_verbs = message.add_subparsers(dest="verb", required=True)
    m_draft = message_verbs.add_parser(
        "draft", parents=[common], help="render a chase draft — never sends"
    )
    m_draft.add_argument("--template", required=True, help="template name")
    m_draft.add_argument("--tenancy-id")
    m_draft.add_argument("--month")
    m_draft.add_argument("--tenant-name")
    m_draft.add_argument("--amount-short")
    m_draft.add_argument("--output", help="write the draft to a file (default stdout)")
    m_draft.add_argument("--templates-dir", help="directory holding <name>.txt templates")
    m_draft.set_defaults(func=cmd_draft, needs_auth=False)

    return parser


def main(argv=None, transport=None, op_runner=None, feishu=None,
         stdout=None, stderr=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse usage error: already printed to stderr; maps to validation (exit 1),
        # not argparse's 2 — 2 means AUTH in this CLI's contract.
        return 1 if exc.code in (2, None) else int(exc.code)
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr

    try:
        config = load_config(getattr(args, "config", None))
        if getattr(args, "endpoint", None):
            config["base_url"] = args.endpoint
        if getattr(args, "token_source", None):
            config["token"]["source"] = args.token_source

        ctx = {
            "config": config,
            "out": out,
            "err": err,
            "client": None,
            "audit": AuditLog(config["audit"]["path"]),
            "feishu": feishu or Feishu.from_config(config["feishu"], transport=transport),
        }

        if getattr(args, "needs_auth", False):
            token = fetch_token(config, op_runner=op_runner)
            ctx["client"] = CosyfloClient(
                config["base_url"], token, transport=transport or requests.Session()
            )

        return args.func(args, ctx) or 0
    except CliError as exc:
        print(f"error: {exc.message}", file=err)
        return exc.exit_code
    except Exception as exc:
        print(f"error: unexpected failure: {exc}", file=err)
        return 5


if __name__ == "__main__":
    sys.exit(main())