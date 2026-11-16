"""Private employee messages for the VB client."""
import hashlib
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pyodbc
from flask import Blueprint, abort, current_app, g, jsonify, request
from services.lims_auth_service import LIMS_CONNECTION_STRING, validate_lims_user

bp = Blueprint("internal_messages", __name__, url_prefix="/api/internal-messages")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    digest TEXT PRIMARY KEY, employee TEXT NOT NULL, expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY, sender TEXT NOT NULL, recipient TEXT NOT NULL,
    body TEXT NOT NULL, sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at TEXT
);
CREATE TABLE IF NOT EXISTS message_clear (
    employee TEXT NOT NULL, peer TEXT NOT NULL, through_id INTEGER NOT NULL,
    PRIMARY KEY (employee, peer)
);
CREATE INDEX IF NOT EXISTS inbox ON messages(recipient, read_at, id);
CREATE INDEX IF NOT EXISTS outbox ON messages(sender, recipient, id);
"""

@contextmanager
def storage():
    path = Path(current_app.instance_path)
    path.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path / "internal_messages.sqlite3"))
    db.row_factory = sqlite3.Row
    try:
        db.executescript(SCHEMA)
        with db:
            yield db
    finally:
        db.close()


def digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@bp.before_request
def authorize():
    # Configure the HTTPS reverse proxy to set this header and keep this
    # blueprint's upstream inaccessible to direct network clients.
    if not request.is_secure and not (
        request.remote_addr in ("127.0.0.1", "::1")
        and request.headers.get("X-Forwarded-Proto") == "https"
    ):
        abort(403)
    if request.endpoint == "internal_messages.sign_in":
        return
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer ") or len(header) > 128:
        abort(401)
    g.message_session = digest(header[7:])
    with storage() as db:
        row = db.execute(
            "SELECT employee FROM sessions WHERE digest=? AND expires > strftime('%s','now')",
            (g.message_session,),
        ).fetchone()
    if row is None:
        abort(401)
    g.message_employee = row["employee"]


@bp.after_request
def prevent_caching(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.errorhandler(400)
@bp.errorhandler(401)
@bp.errorhandler(403)
@bp.errorhandler(404)
def json_error(error):
    return jsonify(error=error.name), error.code


def payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400)
    return data


@bp.post("/session")
def sign_in():
    data = payload()
    user_id = data.get("user_id")
    password = data.get("password")
    if not isinstance(user_id, str) or not isinstance(password, str):
        abort(400)
    if not 1 <= len(user_id.strip()) <= 128 or not 1 <= len(password) <= 256:
        abort(400)
    user = validate_lims_user(user_id, password)
    if not user or not user.get("employee_id"):
        abort(401)
    employee = str(user["employee_id"]).strip()
    token = secrets.token_urlsafe(32)
    with storage() as db:
        db.execute("DELETE FROM sessions WHERE expires <= strftime('%s','now')")
        db.execute(
            "INSERT INTO sessions VALUES (?, ?, strftime('%s','now') + 28800)",
            (digest(token), employee),
        )
    return jsonify(token=token, employee_id=employee)


@bp.delete("/session")
def sign_out():
    with storage() as db:
        db.execute("DELETE FROM sessions WHERE digest=?", (g.message_session,))
    return "", 204


@bp.get("/employees")
def employees():
    term = request.args.get("q", "").strip()
    if not 1 <= len(term) <= 80:
        abort(400)
    conn = pyodbc.connect(LIMS_CONNECTION_STRING)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT FIRST 30 E.EMPID, E.EMPNAME, D.DEPTNAME
               FROM EMPLOY E LEFT JOIN DEPARTMENT D ON D.DEPTNO=E.DEPTNO
               WHERE E.EMPID <> ? AND (E.EMPID STARTING WITH ? OR E.EMPNAME CONTAINING ?)
               AND EXISTS (SELECT 1 FROM SYS_USER U WHERE U.TAKENO=E.EMPID)
               ORDER BY E.EMPNAME, E.EMPID""",
            g.message_employee, term, term,
        )
        rows = [dict(employee_id=str(r[0]).strip(), name=str(r[1] or "").strip(),
                     department=str(r[2] or "").strip()) for r in cursor]
    finally:
        conn.close()
    return jsonify(employees=rows)


@bp.get("/unread")
def unread():
    with storage() as db:
        row = db.execute(
            """SELECT COUNT(*) AS count, MAX(m.id) AS latest_id
               FROM messages m LEFT JOIN message_clear c
                 ON c.employee=m.recipient AND c.peer=m.sender
               WHERE m.recipient=? AND m.read_at IS NULL
                 AND m.id > COALESCE(c.through_id, 0)""",
            (g.message_employee,),
        ).fetchone()
    return jsonify(dict(row))


@bp.get("/messages")
def messages():
    before = request.args.get("before", default=9223372036854775807, type=int)
    if not 1 <= before <= 9223372036854775807:
        abort(400)
    peer = request.args.get("peer", "").strip()
    employee = g.message_employee
    with storage() as db:
        rows = db.execute(
            """SELECT m.* FROM messages m LEFT JOIN message_clear c
                 ON c.employee=? AND c.peer=CASE WHEN m.sender=? THEN m.recipient ELSE m.sender END
               WHERE m.id < ? AND (m.sender=? OR m.recipient=?)
                 AND (?='' OR CASE WHEN m.sender=? THEN m.recipient ELSE m.sender END=?)
                 AND m.id > COALESCE(c.through_id, 0)
               ORDER BY m.id DESC LIMIT 100""",
            (employee, employee, before, employee, employee, peer, employee, peer),
        ).fetchall()
    return jsonify(messages=[dict(row) for row in rows])


@bp.post("/messages/clear")
def clear_conversation():
    peer = payload().get("peer")
    if not isinstance(peer, str):
        abort(400)
    peer = peer.strip()
    employee = g.message_employee
    if not 1 <= len(peer) <= 80 or peer == employee:
        abort(400)
    with storage() as db:
        db.execute(
            """INSERT OR REPLACE INTO message_clear(employee, peer, through_id)
               SELECT ?, ?, MAX(id) FROM messages
               WHERE (sender=? AND recipient=?) OR (sender=? AND recipient=?)
               HAVING COUNT(*) > 0""",
            (employee, peer, employee, peer, peer, employee),
        )
    return "", 204


@bp.post("/messages")
def send_message():
    data = payload()
    recipient, body = data.get("recipient"), data.get("body")
    if not isinstance(recipient, str) or not isinstance(body, str):
        abort(400)
    recipient, body = recipient.strip(), body.strip()
    if not 1 <= len(recipient) <= 80 or recipient == g.message_employee or not 1 <= len(body) <= 4000:
        abort(400)
    conn = pyodbc.connect(LIMS_CONNECTION_STRING)
    try:
        row = conn.cursor().execute(
            """SELECT E.EMPID FROM EMPLOY E WHERE E.EMPID=?
               AND EXISTS (SELECT 1 FROM SYS_USER U WHERE U.TAKENO=E.EMPID)""",
            recipient,
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        abort(404)
    recipient = str(row[0]).strip()
    if recipient == g.message_employee:
        abort(400)
    with storage() as db:
        cursor = db.execute("INSERT INTO messages(sender, recipient, body) VALUES (?, ?, ?)",
                            (g.message_employee, recipient, body))
        message_id = cursor.lastrowid
    return jsonify(id=message_id), 201


@bp.post("/messages/<int:message_id>/read")
def mark_read(message_id):
    if not 1 <= message_id <= 9223372036854775807:
        abort(404)
    with storage() as db:
        cursor = db.execute(
            """UPDATE messages SET read_at=COALESCE(read_at, CURRENT_TIMESTAMP)
               WHERE id=? AND recipient=? AND id > COALESCE(
                   (SELECT through_id FROM message_clear c
                    WHERE c.employee=messages.recipient AND c.peer=messages.sender), 0)""",
            (message_id, g.message_employee),
        )
        if not cursor.rowcount:
            abort(404)
    return "", 204
