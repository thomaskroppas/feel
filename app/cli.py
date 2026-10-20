"""Консольные команды.

    python -m app.cli create-user EMAIL [--admin] [--timezone Europe/Moscow]
    python -m app.cli set-password EMAIL
    python -m app.cli gen-vapid
    python -m app.cli send-due          # запускается cron раз в 5 минут
"""
import argparse
import base64
import fcntl
import getpass
import logging
import sys

from sqlalchemy import select


def _db():
    from . import db as app_db
    return app_db.SessionLocal()


def cmd_create_user(args) -> int:
    from .services.users import create_user
    from .timeutil import is_valid_tz

    if args.timezone and not is_valid_tz(args.timezone):
        print(f"Неизвестный часовой пояс: {args.timezone}", file=sys.stderr)
        return 1
    password = args.password or getpass.getpass("Пароль: ")
    if not args.password and password != getpass.getpass("Ещё раз: "):
        print("Пароли не совпадают", file=sys.stderr)
        return 1
    if len(password) < 8:
        print("Пароль — не короче 8 символов", file=sys.stderr)
        return 1
    db = _db()
    try:
        user = create_user(db, args.email, password, is_admin=args.admin, timezone=args.timezone)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    finally:
        db.close()
    print(f"Создан пользователь {user.email} (id {user.id})")
    return 0


def cmd_set_password(args) -> int:
    from . import models
    from .security import hash_password

    password = getpass.getpass("Новый пароль: ")
    if password != getpass.getpass("Ещё раз: ") or len(password) < 8:
        print("Пароли не совпадают или короче 8 символов", file=sys.stderr)
        return 1
    db = _db()
    try:
        user = db.scalar(select(models.User).where(models.User.email == args.email.strip().lower()))
        if user is None:
            print("Нет такого пользователя", file=sys.stderr)
            return 1
        user.password_hash = hash_password(password)
        db.commit()
    finally:
        db.close()
    print("Пароль изменён")
    return 0


def cmd_gen_vapid(args) -> int:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    raw_private = key.private_numbers().private_value.to_bytes(32, "big")
    raw_public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)

    def b64(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    print("# Добавьте в .env:")
    print(f"VAPID_PRIVATE_KEY={b64(raw_private)}")
    print(f"VAPID_PUBLIC_KEY={b64(raw_public)}")
    return 0


def cmd_send_due(args) -> int:
    from .config import settings
    from .services.notify import run_due

    settings.var_dir.mkdir(parents=True, exist_ok=True)
    lock = open(settings.var_dir / "send-due.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0  # предыдущий запуск ещё идёт
    db = _db()
    try:
        for s in run_due(db):
            print(f"{s.local_date} user={s.user_id} {s.kind}: {s.status}")
    finally:
        db.close()
        lock.close()
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="python -m app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create-user", help="создать пользователя")
    c.add_argument("email")
    c.add_argument("--admin", action="store_true")
    c.add_argument("--timezone", default=None)
    c.add_argument("--password", default=None, help=argparse.SUPPRESS)
    c.set_defaults(func=cmd_create_user)

    c = sub.add_parser("set-password", help="сменить пароль")
    c.add_argument("email")
    c.set_defaults(func=cmd_set_password)

    sub.add_parser("gen-vapid", help="сгенерировать ключи VAPID").set_defaults(func=cmd_gen_vapid)
    sub.add_parser("send-due", help="разослать уведомления (cron)").set_defaults(func=cmd_send_due)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
