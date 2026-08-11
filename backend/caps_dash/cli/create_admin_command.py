"""`caps-dash create-admin`.

The password is prompted or generated - never a default baked into source.
The reference project shipped `quantri / caps@2026` in a Python file that was
then published to GitHub, which is precisely what this command exists to
replace.
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import sys
from typing import Any

from ..config.settings import get_settings
from ..db.engine_factory import create_db_engine
from ..db.enums import UserRole
from ..db.session import create_session_factory, session_scope
from ..repositories import user_repository
from ..services import user_service


def add_create_admin_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser("create-admin", help="Create an administrator account")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--display-name", default="Administrator")
    parser.add_argument(
        "--generate-password",
        action="store_true",
        help="Generate a strong password and print it once instead of prompting",
    )
    parser.set_defaults(handler=run_create_admin)


def run_create_admin(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    factory = create_session_factory(engine)

    try:
        with session_scope(factory) as session:
            if user_repository.get_by_username(session, args.username.lower()) is not None:
                print(f"User {args.username!r} already exists.", file=sys.stderr)
                return 1

            password = _obtain_password(generate=args.generate_password)
            if password is None:
                return 1

            user_service.create_user(
                session,
                username=args.username,
                password=password,
                display_name=args.display_name,
                role=UserRole.ADMIN,
            )
    finally:
        engine.dispose()

    print(f"Created administrator {args.username!r}.")
    return 0


def _obtain_password(*, generate: bool) -> str | None:
    if generate:
        password = secrets.token_urlsafe(16)
        print("Generated password (shown once, store it now):")
        print(f"  {password}")
        return password

    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Confirm password: "):
        print("Passwords did not match.", file=sys.stderr)
        return None
    if len(password) < user_service.MIN_PASSWORD_LENGTH:
        print(
            f"Password must be at least {user_service.MIN_PASSWORD_LENGTH} characters.",
            file=sys.stderr,
        )
        return None
    return password
