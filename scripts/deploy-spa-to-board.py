"""Deploy the built SPA to the UNO Q board and restart the service.

    .venv/Scripts/python.exe scripts/deploy-spa-to-board.py

The board does NOT use the packaged layout `docs/deployment-guide.md`
describes: there is no `/etc/caps-dash/` and no `/var/lib/caps-dash/`.
Everything lives under `/home/arduino/caps-dash`, and the systemd unit runs
that directory's own `.venv`. The SPA therefore goes to
`/home/arduino/caps-dash/frontend/dist`, not to a packaged share directory.

Authentication prefers the deploy key at `~/.ssh/unoq`. When no key is
installed yet, set `CAPS_BOARD_PASSWORD_FILE` to a file holding the password
and this script installs the public key on its way through, so the next run
needs no password. The password is read from a file rather than an argument
or an environment value so it never lands in a process listing or a shell
history, and the file belongs outside this repository.

The previous bundle is renamed to `dist.prev` rather than deleted: a bad
deploy is then one `mv` away from being undone, without a rebuild.
"""

from __future__ import annotations

import os
import posixpath
import sys
from pathlib import Path

import paramiko

HOST = os.environ.get("CAPS_BOARD_HOST", "192.168.137.37")
USER = os.environ.get("CAPS_BOARD_USER", "arduino")
REMOTE_ROOT = "/home/arduino/caps-dash"
REMOTE_DIST = posixpath.join(REMOTE_ROOT, "frontend", "dist")
LOCAL_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
DEPLOY_KEY = Path.home() / ".ssh" / "unoq"
SERVICE = "caps-dash"


def _password() -> str | None:
    """The board password, or None when only key auth is available."""
    path = os.environ.get("CAPS_BOARD_PASSWORD_FILE")
    if not path:
        return None
    return Path(path).read_text(encoding="utf-8").strip()


def connect(password: str | None) -> paramiko.SSHClient:
    """Key first, password only as the fallback that installs the key."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if DEPLOY_KEY.is_file():
        try:
            client.connect(HOST, username=USER, key_filename=str(DEPLOY_KEY), timeout=20)
            print(f"connected to {USER}@{HOST} with {DEPLOY_KEY.name}")
            return client
        except paramiko.AuthenticationException:
            if password is None:
                raise
    if password is None:
        raise SystemExit(
            "No usable deploy key and no CAPS_BOARD_PASSWORD_FILE set - cannot authenticate."
        )
    client.connect(HOST, username=USER, password=password, timeout=20)
    print(f"connected to {USER}@{HOST} with a password")
    return client


def run(
    client: paramiko.SSHClient, command: str, *, sudo: bool = False, password: str | None = None
) -> tuple[int, str]:
    """Run one command, feeding sudo its password on stdin when asked."""
    if sudo:
        # -S takes the password from stdin; -p '' keeps the prompt out of stderr.
        command = f"sudo -S -p '' {command}"
    stdin, stdout, stderr = client.exec_command(command, timeout=180)
    if sudo and password is not None:
        stdin.write(password + "\n")
        stdin.flush()
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    return stdout.channel.recv_exit_status(), (out + err).strip()


def install_deploy_key(client: paramiko.SSHClient) -> None:
    """Append the public key to authorized_keys, once, idempotently."""
    pub = DEPLOY_KEY.with_suffix(".pub")
    if not pub.is_file():
        print("no public key to install; skipping")
        return
    line = pub.read_text(encoding="utf-8").strip()
    run(client, "mkdir -p ~/.ssh && chmod 700 ~/.ssh")
    code, _ = run(
        client,
        f"grep -qF '{line}' ~/.ssh/authorized_keys 2>/dev/null || echo '{line}' "
        ">> ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys",
    )
    print("deploy key present on board:", code == 0)


def upload_tree(sftp: paramiko.SFTPClient, local: Path, remote: str) -> int:
    """Mirror a local directory onto the board, creating directories as needed."""
    uploaded = 0
    for path in sorted(local.rglob("*")):
        target = posixpath.join(remote, path.relative_to(local).as_posix())
        if path.is_dir():
            try:
                sftp.stat(target)
            except FileNotFoundError:
                sftp.mkdir(target)
            continue
        sftp.put(str(path), target)
        uploaded += 1
    return uploaded


def main() -> int:
    if not (LOCAL_DIST / "index.html").is_file():
        raise SystemExit(f"No built SPA at {LOCAL_DIST} - run `npm run build` in frontend/ first.")

    password = _password()
    client = connect(password)

    _, board = run(client, "hostname; uname -m")
    print("board:", board.replace("\n", " "))
    install_deploy_key(client)

    # Keep the outgoing bundle rather than deleting it, so a rollback is a
    # rename and does not need this machine or a rebuild.
    run(client, f"rm -rf {REMOTE_DIST}.prev")
    run(client, f"test -d {REMOTE_DIST} && mv {REMOTE_DIST} {REMOTE_DIST}.prev")
    run(client, f"mkdir -p {REMOTE_DIST}")

    sftp = client.open_sftp()
    try:
        uploaded = upload_tree(sftp, LOCAL_DIST, REMOTE_DIST)
    finally:
        sftp.close()
    print("uploaded files:", uploaded)

    code, out = run(client, f"systemctl restart {SERVICE}", sudo=True, password=password)
    if code != 0:
        print("restart failed:", out[:300])
    _, active = run(client, f"systemctl is-active {SERVICE}")
    print("service:", active)

    client.close()
    return 0 if active.strip() == "active" else 1


if __name__ == "__main__":
    sys.exit(main())
