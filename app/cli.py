"""Администрирование с сервера: sudo pdfdisplay-admin set-password admin"""
import argparse
import getpass
import re
import sqlite3
import sys

from core import connect, hash_password, init_db, now, transaction


def read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("Новый пароль: ")
    if first != getpass.getpass("Ещё раз: "):
        sys.exit("Пароли не совпадают")
    return first


def main() -> None:
    parser = argparse.ArgumentParser(prog="pdfdisplay-admin")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("set-password", help="создать пользователя или сменить ему пароль")
    sp.add_argument("username")
    sp.add_argument("--stdin", action="store_true", help="прочитать пароль из stdin")
    sub.add_parser("users", help="список пользователей")
    rp = sub.add_parser("rename", help="сменить логин пользователя")
    rp.add_argument("old_username")
    rp.add_argument("new_username")
    args = parser.parse_args()

    init_db()
    db = connect()
    if args.cmd == "users":
        for row in db.execute("SELECT username FROM users ORDER BY username"):
            print(row["username"])
        return
    if args.cmd == "rename":
        if not re.match(r"^[A-Za-z0-9._@-]{3,64}$", args.new_username):
            sys.exit("Логин: от 3 до 64 символов, латинские буквы, цифры и . _ @ -")
        try:
            cur = db.execute("UPDATE users SET username = ? WHERE username = ?", (args.new_username, args.old_username))
        except sqlite3.IntegrityError:
            sys.exit(f"Логин {args.new_username} уже занят")
        if cur.rowcount == 0:
            sys.exit(f"Пользователь {args.old_username} не найден")
        print(f"Логин {args.old_username} изменён на {args.new_username}")
        return

    password = read_password(args.stdin)
    if len(password) < 10:
        sys.exit("Пароль должен быть не короче 10 символов")
    with transaction(db):
        row = db.execute("SELECT id FROM users WHERE username = ?", (args.username,)).fetchone()
        if row:
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), row["id"]))
            # Смена пароля завершает все открытые входы этого пользователя.
            db.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
            print(f"Пароль пользователя {args.username} изменён")
        else:
            db.execute("INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                       (args.username, hash_password(password), now()))
            print(f"Пользователь {args.username} создан")


if __name__ == "__main__":
    main()
