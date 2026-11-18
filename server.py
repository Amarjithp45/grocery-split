#!/usr/bin/env python3
"""
SPLITKART - Collaborative Grocery Shopping & Bill-Splitting Server
Features:
- Permanent HMAC-Signed Session Tokens (Never times out, immune to server restarts)
- Auto-restores user identity and session on database recreation
- User Registration & Authentication (salted SHA-256) — email-based username
- Groups System: Create / Join groups via invite codes
- Permanent Admin: amarjithp45@gmail.com is always admin
- Robust Admin Member Removal (safely cleans all dependencies)
- Identity locking (users can only act as themselves)
- Server-Sent Events (SSE) for instant push updates
- REST API for items, bills, debts, and settlements (Euro € currency)
"""

import os
import sys
import json
import sqlite3
import socket
import threading
import queue
import mimetypes
import hashlib
import hmac
import base64
import secrets
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# Base paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DB_PATH = os.path.join(BASE_DIR, "grocery.db")

# Permanent Server Secret for HMAC Session Tokens (10-year validity)
SECRET_KEY = os.environ.get("SECRET_KEY", "SPLITKART-permanent-secret-key-2026-v1-xyz")

# Permanent admin email — always admin regardless of DB value
PERMANENT_ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "amarjithp45@gmail.com")

# Thread-safe SSE client subscriptions
sse_subscribers = []
sse_lock = threading.Lock()

def broadcast_event(event_type: str, data: dict):
    """Broadcast an SSE event to all connected clients."""
    payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    with sse_lock:
        dead_queues = []
        for q in sse_subscribers:
            try:
                q.put_nowait(payload)
            except Exception:
                dead_queues.append(q)
        for q in dead_queues:
            if q in sse_subscribers:
                sse_subscribers.remove(q)

def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """Hash password using standard library SHA-256 with cryptographic salt."""
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
    return hashed, salt

def generate_invite_code():
    """Generate a random 8-character invite code."""
    return secrets.token_urlsafe(6).upper()[:8]

def is_permanent_admin(username: str) -> bool:
    """Return True if username matches the permanent admin email."""
    if not username:
        return False
    return username.strip().lower() == PERMANENT_ADMIN_EMAIL.lower()

def create_session_token(user_dict: dict) -> str:
    """Generate a permanent HMAC-signed token that never expires."""
    # Always enforce admin for permanent admin email
    is_admin = int(user_dict.get("is_admin", 0))
    if is_permanent_admin(user_dict.get("username", "")):
        is_admin = 1
    clean_user = {
        "id": int(user_dict["id"]),
        "name": str(user_dict["name"]),
        "username": str(user_dict.get("username", "")),
        "avatar_color": str(user_dict.get("avatar_color", "#10b981")),
        "is_admin": is_admin
    }
    payload_str = json.dumps(clean_user, separators=(',', ':'))
    payload_b64 = base64.urlsafe_b64encode(payload_str.encode('utf-8')).decode('utf-8').rstrip('=')
    signature = hmac.new(SECRET_KEY.encode('utf-8'), payload_b64.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"

def verify_session_token(token: str) -> dict:
    """Verify HMAC-signed session token. Valid indefinitely."""
    if not token or "." not in token:
        return None
    try:
        payload_b64, signature = token.split(".", 1)
        expected_sig = hmac.new(SECRET_KEY.encode('utf-8'), payload_b64.encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
        rem = len(payload_b64) % 4
        padded = payload_b64 + ('=' * (4 - rem) if rem else '')
        payload_bytes = base64.urlsafe_b64decode(padded)
        return json.loads(payload_bytes.decode('utf-8'))
    except Exception:
        return None

def get_db():
    """Get a thread-local SQLite connection with dictionary-like row access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    """Initialize database tables, ensure schema migrations for auth & admin tracking."""
    conn = get_db()
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                username TEXT UNIQUE,
                password_hash TEXT,
                salt TEXT,
                avatar_color TEXT NOT NULL DEFAULT '#10b981',
                is_admin INTEGER DEFAULT 0,
                last_login TIMESTAMP,
                last_active TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration check for members table
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(members)")
        cols = [r["name"] for r in cur.fetchall()]
        if "username" not in cols:
            conn.execute("ALTER TABLE members ADD COLUMN username TEXT")
        if "password_hash" not in cols:
            conn.execute("ALTER TABLE members ADD COLUMN password_hash TEXT")
        if "salt" not in cols:
            conn.execute("ALTER TABLE members ADD COLUMN salt TEXT")
        if "is_admin" not in cols:
            conn.execute("ALTER TABLE members ADD COLUMN is_admin INTEGER DEFAULT 0")
        if "last_login" not in cols:
            conn.execute("ALTER TABLE members ADD COLUMN last_login TIMESTAMP")
        if "last_active" not in cols:
            conn.execute("ALTER TABLE members ADD COLUMN last_active TIMESTAMP")

        # Always ensure the permanent admin email has is_admin = 1
        conn.execute(
            "UPDATE members SET is_admin = 1 WHERE LOWER(username) = LOWER(?)",
            (PERMANENT_ADMIN_EMAIL,)
        )

        # Pre-seed/guarantee the permanent admin account with Amar@2003 password
        admin_row = conn.execute("SELECT id FROM members WHERE LOWER(username) = LOWER(?)", (PERMANENT_ADMIN_EMAIL,)).fetchone()
        admin_hash, admin_salt = hash_password("Amar@2003")
        if not admin_row:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO members (name, username, password_hash, salt, avatar_color, is_admin)
                VALUES (?, ?, ?, ?, ?, 1)
            """, ("Amar", PERMANENT_ADMIN_EMAIL, admin_hash, admin_salt, "#059669"))
            admin_id = cur.lastrowid
        else:
            admin_id = admin_row["id"]
            conn.execute("""
                UPDATE members SET password_hash = ?, salt = ?, is_admin = 1
                WHERE LOWER(username) = LOWER(?)
            """, (admin_hash, admin_salt, PERMANENT_ADMIN_EMAIL))

        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                member_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
            )
        """)

        # Groups tables
        conn.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                invite_code TEXT UNIQUE NOT NULL,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES members(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS group_members (
                group_id INTEGER NOT NULL,
                member_id INTEGER NOT NULL,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, member_id),
                FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
                FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                quantity TEXT DEFAULT '1',
                category TEXT DEFAULT 'Pantry',
                is_urgent INTEGER DEFAULT 0,
                added_by INTEGER,
                is_bought INTEGER DEFAULT 0,
                bought_by INTEGER,
                bought_at TIMESTAMP,
                purchased_qty TEXT,
                group_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (added_by) REFERENCES members(id),
                FOREIGN KEY (bought_by) REFERENCES members(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS bills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_name TEXT NOT NULL,
                total_amount REAL NOT NULL,
                paid_by INTEGER NOT NULL,
                bill_date TEXT NOT NULL,
                notes TEXT DEFAULT '',
                group_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (paid_by) REFERENCES members(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS bill_splits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bill_id INTEGER NOT NULL,
                member_id INTEGER NOT NULL,
                share_amount REAL NOT NULL,
                FOREIGN KEY (bill_id) REFERENCES bills(id) ON DELETE CASCADE,
                FOREIGN KEY (member_id) REFERENCES members(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS settlements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_member_id INTEGER NOT NULL,
                to_member_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                note TEXT DEFAULT '',
                group_id INTEGER,
                settled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (from_member_id) REFERENCES members(id),
                FOREIGN KEY (to_member_id) REFERENCES members(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                action_type TEXT NOT NULL,
                member_id INTEGER,
                group_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (member_id) REFERENCES members(id)
            )
        """)

        # Migration: add group_id column to existing tables if missing
        for table in ["items", "bills", "settlements", "activities"]:
            cur.execute(f"PRAGMA table_info({table})")
            tcols = [r["name"] for r in cur.fetchall()]
            if "group_id" not in tcols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN group_id INTEGER")

        # Migration: add purchased_qty to items if missing
        cur.execute("PRAGMA table_info(items)")
        item_cols = [r["name"] for r in cur.fetchall()]
        if "purchased_qty" not in item_cols:
            conn.execute("ALTER TABLE items ADD COLUMN purchased_qty TEXT")

        # Ensure at least one group exists and link existing unassigned items to it
        default_grp = conn.execute("SELECT id FROM groups LIMIT 1").fetchone()
        if not default_grp:
            cur = conn.cursor()
            code = generate_invite_code()
            cur.execute("INSERT INTO groups (name, invite_code, created_by) VALUES (?, ?, ?)", ("Main Group", code, admin_id))
            first_grp_id = cur.lastrowid
            cur.execute("INSERT OR IGNORE INTO group_members (group_id, member_id) VALUES (?, ?)", (first_grp_id, admin_id))
            conn.execute("INSERT OR IGNORE INTO group_members (group_id, member_id) SELECT ?, id FROM members", (first_grp_id,))
            for table in ["items", "bills", "settlements", "activities"]:
                conn.execute(f"UPDATE {table} SET group_id = ? WHERE group_id IS NULL", (first_grp_id,))
        else:
            first_grp_id = default_grp["id"]
            conn.execute("INSERT OR IGNORE INTO group_members (group_id, member_id) VALUES (?, ?)", (first_grp_id, admin_id))
            for table in ["items", "bills", "settlements", "activities"]:
                conn.execute(f"UPDATE {table} SET group_id = ? WHERE group_id IS NULL", (first_grp_id,))

    conn.close()

def log_activity(conn, message: str, action_type: str, member_id=None, group_id=None):
    """Record an action in the activity log."""
    conn.execute(
        "INSERT INTO activities (message, action_type, member_id, group_id) VALUES (?, ?, ?, ?)",
        (message, action_type, member_id, group_id)
    )

def get_authenticated_member(headers, touch_active=False):
    """
    Identify the logged-in member from the Authorization header or session cookie.
    Validates permanent HMAC token and auto-restores user in DB if missing.
    """
    auth_header = headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    if not token:
        cookie_header = headers.get("Cookie", "")
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith("SPLITKART_token="):
                token = part.split("=", 1)[1].strip()
                break
            elif part.startswith("session_token="):
                token = part.split("=", 1)[1].strip()
                break

    if not token:
        return None

    # 1. First, check permanent HMAC-signed token
    token_user = verify_session_token(token)
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()

    try:
        if token_user:
            user_id = token_user["id"]
            # Look up member in database
            row = conn.execute("""
                SELECT m.id, m.name, m.username, m.avatar_color, m.is_admin, m.last_login, m.last_active
                FROM members m WHERE m.id = ?
            """, (user_id,)).fetchone()

            if not row:
                # Auto-restore user if database was recreated
                restore_is_admin = 1 if is_permanent_admin(token_user.get("username", "")) else token_user.get("is_admin", 0)
                with conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO members (id, name, username, avatar_color, is_admin, last_active, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (user_id, token_user["name"], token_user.get("username", ""), token_user.get("avatar_color", "#10b981"), restore_is_admin, now_str, now_str))
                row = conn.execute("SELECT * FROM members WHERE id = ?", (user_id,)).fetchone()

            user_dict = dict(row) if row else token_user

            # Enforce permanent admin
            if is_permanent_admin(user_dict.get("username", "")):
                user_dict["is_admin"] = 1

            if touch_active:
                conn.execute("UPDATE members SET last_active = ? WHERE id = ?", (now_str, user_dict["id"]))
                conn.commit()

            return user_dict

        # 2. Fallback: check sessions table (for legacy tokens)
        row = conn.execute("""
            SELECT m.id, m.name, m.username, m.avatar_color, m.is_admin, m.last_login, m.last_active
            FROM sessions s
            JOIN members m ON s.member_id = m.id
            WHERE s.token = ?
        """, (token,)).fetchone()

        if row:
            user_dict = dict(row)
            if is_permanent_admin(user_dict.get("username", "")):
                user_dict["is_admin"] = 1

            if touch_active:
                conn.execute("UPDATE members SET last_active = ? WHERE id = ?", (now_str, user_dict["id"]))
                conn.commit()

            return user_dict

        return None
    finally:
        conn.close()

def calculate_debt_transfers(members, net_balances):
    """Minimizes debt transfers between members using greedy reconciliation."""
    name_map = {m["id"]: m["name"] for m in members}
    debtors = []
    creditors = []

    for mid, bal in net_balances.items():
        rounded = round(bal, 2)
        if rounded < -0.01:
            debtors.append({"id": mid, "name": name_map.get(mid, "Unknown"), "amount": -rounded})
        elif rounded > 0.01:
            creditors.append({"id": mid, "name": name_map.get(mid, "Unknown"), "amount": rounded})

    debtors.sort(key=lambda x: x["amount"], reverse=True)
    creditors.sort(key=lambda x: x["amount"], reverse=True)

    transfers = []
    i, j = 0, 0
    while i < len(debtors) and j < len(creditors):
        debtor = debtors[i]
        creditor = creditors[j]
        amount = min(debtor["amount"], creditor["amount"])
        if amount > 0.01:
            transfers.append({
                "from_id": debtor["id"],
                "from_name": debtor["name"],
                "to_id": creditor["id"],
                "to_name": creditor["name"],
                "amount": round(amount, 2)
            })
            debtor["amount"] -= amount
            creditor["amount"] -= amount

        if debtor["amount"] <= 0.01:
            i += 1
        if creditor["amount"] <= 0.01:
            j += 1

    return transfers

def get_user_groups(user_id):
    """Get all groups for a user with member counts."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT g.id, g.name, g.invite_code,
                   (SELECT COUNT(*) FROM group_members gm2 WHERE gm2.group_id = g.id) AS member_count
            FROM groups g
            JOIN group_members gm ON g.id = gm.group_id
            WHERE gm.member_id = ?
            ORDER BY g.created_at ASC
        """, (user_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def get_full_state(current_user=None, group_id=None):
    """Retrieve full application state for client consumption."""
    conn = get_db()
    try:
        now_utc = datetime.utcnow()

        user_groups = get_user_groups(current_user["id"]) if current_user else []

        # Determine effective group_id:
        # If group_id is not specified, default to user's first group if they have one; else 0 (Personal)
        if group_id is None or group_id == "" or str(group_id).lower() == "none":
            group_id = user_groups[0]["id"] if user_groups else 0
        else:
            try:
                group_id = int(group_id)
            except (ValueError, TypeError):
                group_id = 0

        group_info = None
        if group_id > 0:
            group_row = conn.execute("SELECT id, name, invite_code FROM groups WHERE id = ?", (group_id,)).fetchone()
            if group_row:
                group_info = dict(group_row)
            else:
                group_id = 0

        if group_id == 0:
            group_info = {"id": 0, "name": "Personal List", "invite_code": ""}
            members = []
            if current_user:
                m_copy = dict(current_user)
                m_copy["is_online"] = True
                m_copy["items_added_count"] = 0
                m_copy["items_bought_count"] = 0
                members.append(m_copy)

            if current_user:
                items_query = """
                    SELECT i.*,
                           m1.name AS added_by_name, m1.avatar_color AS added_by_color,
                           m2.name AS bought_by_name, m2.avatar_color AS bought_by_color
                    FROM items i
                    LEFT JOIN members m1 ON i.added_by = m1.id
                    LEFT JOIN members m2 ON i.bought_by = m2.id
                    WHERE (i.group_id IS NULL OR i.group_id = 0 OR i.added_by = ?)
                    ORDER BY i.is_urgent DESC, i.id DESC
                """
                all_items = [dict(r) for r in conn.execute(items_query, (current_user["id"],)).fetchall()]
            else:
                all_items = []
            active_items = [i for i in all_items if not i["is_bought"]]
            bought_items = [i for i in all_items if i["is_bought"]]
            bills = []
            settlements = []
            member_balances = []
            transfers = []
            activities = []
            total_spent = 0.0

        else:
            # Group mode: fetch members in this group
            members_rows = conn.execute("""
                SELECT m.id, m.name, m.username, m.avatar_color, m.is_admin, m.last_login, m.last_active, m.created_at,
                       (SELECT COUNT(*) FROM items WHERE added_by = m.id AND group_id = ?) AS items_added_count,
                       (SELECT COUNT(*) FROM items WHERE bought_by = m.id AND group_id = ?) AS items_bought_count
                FROM members m
                JOIN group_members gm ON m.id = gm.member_id
                WHERE gm.group_id = ?
                ORDER BY m.is_admin DESC, m.name ASC
            """, (group_id, group_id, group_id)).fetchall()

            members = []
            online_count = 0
            for r in members_rows:
                m = dict(r)
                if is_permanent_admin(m.get("username", "")):
                    m["is_admin"] = 1

                is_online = False
                if m.get("last_active"):
                    try:
                        dt = datetime.strptime(m["last_active"], "%Y-%m-%d %H:%M:%S")
                        if (now_utc - dt).total_seconds() < 300:
                            is_online = True
                    except Exception:
                        pass

                if current_user and m["id"] == current_user["id"]:
                    is_online = True

                if is_online:
                    online_count += 1

                m["is_online"] = is_online
                members.append(m)

            # Items filtered by group
            items_query = """
                SELECT i.*,
                       m1.name AS added_by_name, m1.avatar_color AS added_by_color,
                       m2.name AS bought_by_name, m2.avatar_color AS bought_by_color
                FROM items i
                LEFT JOIN members m1 ON i.added_by = m1.id
                LEFT JOIN members m2 ON i.bought_by = m2.id
                WHERE i.group_id = ?
                ORDER BY i.is_urgent DESC, i.id DESC
            """
            all_items = [dict(r) for r in conn.execute(items_query, (group_id,)).fetchall()]
            active_items = [i for i in all_items if not i["is_bought"]]
            bought_items = [i for i in all_items if i["is_bought"]]

            # Bills with splits filtered by group
            bills_rows = conn.execute("""
                SELECT b.*, m.name AS paid_by_name, m.avatar_color AS paid_by_color
                FROM bills b
                JOIN members m ON b.paid_by = m.id
                WHERE b.group_id = ?
                ORDER BY b.bill_date DESC, b.id DESC
            """, (group_id,)).fetchall()

            bills = []
            for b in bills_rows:
                b_dict = dict(b)
                splits = conn.execute("""
                    SELECT bs.*, m.name AS member_name
                    FROM bill_splits bs
                    JOIN members m ON bs.member_id = m.id
                    WHERE bs.bill_id = ?
                """, (b["id"],)).fetchall()
                b_dict["splits"] = [dict(s) for s in splits]
                bills.append(b_dict)

            # Settlements filtered by group
            settlements = [dict(r) for r in conn.execute("""
                SELECT s.*,
                       m1.name AS from_name, m1.avatar_color AS from_color,
                       m2.name AS to_name, m2.avatar_color AS to_color
                FROM settlements s
                JOIN members m1 ON s.from_member_id = m1.id
                JOIN members m2 ON s.to_member_id = m2.id
                WHERE s.group_id = ?
                ORDER BY s.id DESC
                LIMIT 50
            """, (group_id,)).fetchall()]

            # Net balance calculation (in Euros)
            net_balances = {m["id"]: 0.0 for m in members}
            for b in bills:
                net_balances[b["paid_by"]] = net_balances.get(b["paid_by"], 0.0) + b["total_amount"]
                for s in b["splits"]:
                    net_balances[s["member_id"]] = net_balances.get(s["member_id"], 0.0) - s["share_amount"]

            for s in settlements:
                net_balances[s["from_member_id"]] = net_balances.get(s["from_member_id"], 0.0) + s["amount"]
                net_balances[s["to_member_id"]] = net_balances.get(s["to_member_id"], 0.0) - s["amount"]

            member_balances = []
            for m in members:
                mid = m["id"]
                member_balances.append({
                    "id": mid,
                    "name": m["name"],
                    "avatar_color": m["avatar_color"],
                    "balance": round(net_balances.get(mid, 0.0), 2)
                })

            transfers = calculate_debt_transfers(members, net_balances)

            activities = [dict(r) for r in conn.execute("""
                SELECT a.*, m.name AS member_name, m.avatar_color AS member_color
                FROM activities a
                LEFT JOIN members m ON a.member_id = m.id
                WHERE a.group_id = ?
                ORDER BY a.id DESC
                LIMIT 30
            """, (group_id,)).fetchall()]

            total_spent = sum(b["total_amount"] for b in bills)

        return {
            "currentUser": current_user,
            "group": group_info,
            "active_group": group_info,
            "groups": user_groups,
            "needs_group": False,
            "members": members,
            "active_items": active_items,
            "bought_items": bought_items,
            "bills": bills,
            "settlements": settlements,
            "balances": member_balances,
            "transfers": transfers,
            "activities": activities,
            "stats": {
                "active_items_count": len(active_items),
                "bought_items_count": len(bought_items),
                "total_bills_count": len(bills),
                "total_spent": round(total_spent, 2),
                "total_members": len(members),
                "online_members": online_count if group_id > 0 else 1
            }
        }
    finally:
        conn.close()

class SPLITKARTRequestHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def send_json(self, data, status=200, set_cookie_token=None):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if set_cookie_token:
            # 10 years cookie validity
            self.send_header("Set-Cookie", f"SPLITKART_token={set_cookie_token}; Path=/; Max-Age=315360000; SameSite=Lax")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message, status=400):
        self.send_json({"error": message}, status=status)

    def read_json_body(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        raw = self.rfile.read(content_length).decode("utf-8")
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/api/state":
            current_user = get_authenticated_member(self.headers, touch_active=True)
            group_id = qs.get("group_id", [None])[0]
            state = get_full_state(current_user, group_id)
            self.send_json(state)
            return

        if path == "/api/groups":
            current_user = get_authenticated_member(self.headers, touch_active=True)
            if not current_user:
                self.send_error_json("Authentication required.", status=401)
                return
            groups = get_user_groups(current_user["id"])
            self.send_json({"groups": groups})
            return

        if path == "/api/auth/me":
            user = get_authenticated_member(self.headers, touch_active=True)
            if user:
                self.send_json({"authenticated": True, "user": user})
            else:
                self.send_json({"authenticated": False})
            return

        if path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            q = queue.Queue(maxsize=100)
            with sse_lock:
                sse_subscribers.append(q)

            try:
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                while True:
                    try:
                        msg = q.get(timeout=20.0)
                        self.wfile.write(msg.encode("utf-8"))
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                with sse_lock:
                    if q in sse_subscribers:
                        sse_subscribers.remove(q)
            return

        # Serve static assets
        if path == "/" or path == "":
            file_path = os.path.join(STATIC_DIR, "index.html")
        else:
            rel_path = path.lstrip("/")
            file_path = os.path.join(STATIC_DIR, rel_path)

        norm_path = os.path.abspath(file_path)
        if not norm_path.startswith(STATIC_DIR) or not os.path.isfile(norm_path):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")
            return

        content_type, _ = mimetypes.guess_type(norm_path)
        content_type = content_type or "application/octet-stream"

        with open(norm_path, "rb") as f:
            content = f.read()

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self.read_json_body()
        conn = get_db()

        try:
            now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            # -----------------------------------------------------
            # AUTH: Register New Friend (email-based username)
            # -----------------------------------------------------
            if path == "/api/auth/register":
                username = body.get("username", "").strip().lower()
                password = body.get("password", "").strip()
                name = body.get("name", "").strip()

                if not username or len(username) < 3:
                    self.send_error_json("Please use a valid email address as your username.")
                    return
                # Email validation: must contain @ and .
                if "@" not in username or "." not in username.split("@")[-1]:
                    self.send_error_json("Please use a valid email address as your username.")
                    return
                if not password or len(password) < 4:
                    self.send_error_json("Password must be at least 4 characters")
                    return
                if not name:
                    name = username.split("@")[0].capitalize()

                colors = ['#10b981', '#3b82f6', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316']
                avatar_color = colors[len(username) % len(colors)]

                hashed, salt = hash_password(password)

                # Determine is_admin
                is_admin = 1 if is_permanent_admin(username) else 0

                try:
                    with conn:
                        cur = conn.cursor()
                        cur.execute(
                            "INSERT INTO members (name, username, password_hash, salt, avatar_color, is_admin, last_login, last_active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (name, username, hashed, salt, avatar_color, is_admin, now_str, now_str, now_str)
                        )
                        member_id = cur.lastrowid
                        user_obj = {
                            "id": member_id,
                            "name": name,
                            "username": username,
                            "avatar_color": avatar_color,
                            "is_admin": is_admin
                        }
                        # Generate permanent HMAC token (valid forever)
                        token = create_session_token(user_obj)
                        cur.execute("INSERT OR REPLACE INTO sessions (token, member_id) VALUES (?, ?)", (token, member_id))

                        log_msg = f"👑 {name} registered as Admin" if is_admin else f"{name} registered and joined SPLITKART"
                        log_activity(conn, log_msg, "member_joined", member_id)

                    broadcast_event("state_updated", {
                        "action": "member_joined",
                        "name": name,
                        "actor_id": member_id
                    })
                    self.send_json({"success": True, "token": token, "user": user_obj}, set_cookie_token=token)
                except sqlite3.IntegrityError:
                    self.send_error_json("A user with that email already exists.")
                return

            # -----------------------------------------------------
            # AUTH: Login Existing Friend
            # -----------------------------------------------------
            if path == "/api/auth/login":
                username = body.get("username", "").strip().lower()
                password = body.get("password", "").strip()

                if not username or not password:
                    self.send_error_json("Email and password are required")
                    return

                cur = conn.cursor()
                row = cur.execute("SELECT * FROM members WHERE LOWER(username) = ? OR LOWER(name) = ?", (username, username)).fetchone()
                if not row or not row["password_hash"] or not row["salt"]:
                    self.send_error_json("Invalid email or password", status=401)
                    return

                check_hash, _ = hash_password(password, row["salt"])
                if check_hash != row["password_hash"]:
                    self.send_error_json("Invalid email or password", status=401)
                    return

                is_admin = 1 if (is_permanent_admin(row["username"]) or row["is_admin"] == 1) else 0

                user_obj = {
                    "id": row["id"],
                    "name": row["name"],
                    "username": row["username"],
                    "avatar_color": row["avatar_color"],
                    "is_admin": is_admin
                }
                # Generate permanent HMAC token (never times out)
                token = create_session_token(user_obj)

                with conn:
                    conn.execute("INSERT OR REPLACE INTO sessions (token, member_id) VALUES (?, ?)", (token, row["id"]))
                    conn.execute("UPDATE members SET last_login = ?, last_active = ?, is_admin = ? WHERE id = ?", (now_str, now_str, is_admin, row["id"]))
                    log_activity(conn, f"{row['name']} logged in", "member_login", row["id"])

                broadcast_event("state_updated", {
                    "action": "user_logged_in",
                    "actor": row["name"],
                    "actor_id": row["id"]
                })
                self.send_json({"success": True, "token": token, "user": user_obj}, set_cookie_token=token)
                return

            # -----------------------------------------------------
            # AUTH: Logout
            # -----------------------------------------------------
            if path == "/api/auth/logout":
                auth_header = self.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    token = auth_header[7:].strip()
                    with conn:
                        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                self.send_json({"success": True})
                return

            # =====================================================
            # PROTECTED ROUTES (Require Authentication)
            # =====================================================
            current_user = get_authenticated_member(self.headers, touch_active=True)
            if not current_user:
                self.send_error_json("Authentication required. Please log in.", status=401)
                return

            # -----------------------------------------------------
            # GROUPS: Create Group
            # -----------------------------------------------------
            if path == "/api/groups/create":
                group_name = body.get("name", "").strip()
                if not group_name:
                    self.send_error_json("Group name is required")
                    return

                # Generate unique invite code
                invite_code = generate_invite_code()
                # Try a few times to get unique one
                for _ in range(5):
                    existing = conn.execute("SELECT id FROM groups WHERE invite_code = ?", (invite_code,)).fetchone()
                    if not existing:
                        break
                    invite_code = generate_invite_code()

                with conn:
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO groups (name, invite_code, created_by, created_at) VALUES (?, ?, ?, ?)",
                        (group_name, invite_code, current_user["id"], now_str)
                    )
                    group_id = cur.lastrowid
                    cur.execute(
                        "INSERT OR IGNORE INTO group_members (group_id, member_id, joined_at) VALUES (?, ?, ?)",
                        (group_id, current_user["id"], now_str)
                    )
                    log_activity(conn, f"{current_user['name']} created group: {group_name}", "group_created", current_user["id"], group_id)

                broadcast_event("state_updated", {"action": "group_created", "name": group_name, "actor_id": current_user["id"]})
                self.send_json({"success": True, "group": {"id": group_id, "name": group_name, "invite_code": invite_code}})
                return

            # -----------------------------------------------------
            # GROUPS: Join Group via Invite Code
            # -----------------------------------------------------
            if path == "/api/groups/join":
                invite_code = body.get("invite_code", "").strip().upper()
                if not invite_code:
                    self.send_error_json("Invite code is required")
                    return

                group_row = conn.execute(
                    "SELECT * FROM groups WHERE UPPER(invite_code) = ?", (invite_code,)
                ).fetchone()
                if not group_row:
                    self.send_error_json("Invalid invite code. Please check and try again.")
                    return

                group_dict = dict(group_row)
                with conn:
                    conn.execute(
                        "INSERT OR IGNORE INTO group_members (group_id, member_id, joined_at) VALUES (?, ?, ?)",
                        (group_dict["id"], current_user["id"], now_str)
                    )
                    log_activity(conn, f"{current_user['name']} joined group: {group_dict['name']}", "group_joined", current_user["id"], group_dict["id"])

                broadcast_event("state_updated", {"action": "group_joined", "name": group_dict["name"], "actor_id": current_user["id"]})
                self.send_json({"success": True, "group": {"id": group_dict["id"], "name": group_dict["name"], "invite_code": group_dict["invite_code"]}})
                return

            # 1. Add Grocery Item
            if path == "/api/items":
                title = body.get("title", "").strip()
                quantity = body.get("quantity", "1").strip() or "1"
                category = body.get("category", "Pantry").strip() or "Pantry"
                is_urgent = 1 if body.get("is_urgent") else 0
                added_by = current_user["id"]
                raw_gid = body.get("group_id")
                try:
                    group_id = int(raw_gid) if (raw_gid is not None and int(raw_gid) > 0) else None
                except (ValueError, TypeError):
                    group_id = None

                if not title:
                    self.send_error_json("Item name is required")
                    return

                with conn:
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO items (title, quantity, category, is_urgent, added_by, group_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (title, quantity, category, is_urgent, added_by, group_id, now_str)
                    )
                    item_id = cur.lastrowid
                    log_activity(conn, f"{current_user['name']} added: {title} ({quantity})", "item_added", added_by, group_id)

                broadcast_event("state_updated", {
                    "action": "item_added",
                    "title": title,
                    "quantity": quantity,
                    "created_at": now_str,
                    "actor": current_user["name"],
                    "actor_id": current_user["id"],
                    "group_id": group_id
                })
                self.send_json({"success": True, "item_id": item_id})
                return

            # 2. Toggle Item Bought Status
            if path == "/api/items/toggle":
                item_id = body.get("item_id")
                if not item_id:
                    self.send_error_json("item_id is required")
                    return

                purchased_qty = body.get("purchased_qty", None)

                with conn:
                    cur = conn.cursor()
                    item = cur.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
                    if not item:
                        self.send_error_json("Item not found", status=404)
                        return

                    new_status = 0 if item["is_bought"] else 1
                    bought_by = current_user["id"] if new_status == 1 else None
                    bought_at = now_str if new_status == 1 else None
                    pqty = str(purchased_qty).strip() if (new_status == 1 and purchased_qty) else None

                    cur.execute(
                        "UPDATE items SET is_bought = ?, bought_by = ?, bought_at = ?, purchased_qty = ? WHERE id = ?",
                        (new_status, bought_by, bought_at, pqty, item_id)
                    )

                    qty_note = f" ({pqty})" if pqty else ""
                    msg = (
                        f"{current_user['name']} bought: {item['title']}{qty_note}"
                        if new_status
                        else f"{current_user['name']} moved back to cart: {item['title']}"
                    )
                    log_activity(conn, msg, "item_toggled", current_user["id"], item["group_id"])

                broadcast_event("state_updated", {
                    "action": "item_toggled",
                    "title": item["title"],
                    "is_bought": bool(new_status),
                    "bought_at": bought_at,
                    "actor": current_user["name"],
                    "actor_id": current_user["id"]
                })
                self.send_json({"success": True, "is_bought": bool(new_status)})
                return

            # 3. Clear All Bought Items
            if path == "/api/items/clear-bought":
                raw_gid = body.get("group_id")
                try:
                    group_id = int(raw_gid) if (raw_gid is not None and int(raw_gid) > 0) else None
                except (ValueError, TypeError):
                    group_id = None

                with conn:
                    cur = conn.cursor()
                    if group_id:
                        count = cur.execute("SELECT COUNT(*) AS cnt FROM items WHERE is_bought = 1 AND group_id = ?", (group_id,)).fetchone()["cnt"]
                        cur.execute("DELETE FROM items WHERE is_bought = 1 AND group_id = ?", (group_id,))
                    else:
                        count = cur.execute("SELECT COUNT(*) AS cnt FROM items WHERE is_bought = 1 AND (group_id IS NULL OR group_id = 0 OR added_by = ?)", (current_user["id"],)).fetchone()["cnt"]
                        cur.execute("DELETE FROM items WHERE is_bought = 1 AND (group_id IS NULL OR group_id = 0 OR added_by = ?)", (current_user["id"],))
                    log_activity(conn, f"{current_user['name']} cleared {count} purchased item(s)", "cleared_bought", current_user["id"], group_id)

                broadcast_event("state_updated", {
                    "action": "cleared_bought",
                    "count": count,
                    "actor": current_user["name"],
                    "actor_id": current_user["id"]
                })
                self.send_json({"success": True, "cleared_count": count})
                return

            # 4. Delete Single Item
            if path == "/api/items/delete":
                item_id = body.get("item_id")
                if not item_id:
                    self.send_error_json("item_id is required")
                    return
                with conn:
                    cur = conn.cursor()
                    item = cur.execute("SELECT title, group_id FROM items WHERE id = ?", (item_id,)).fetchone()
                    cur.execute("DELETE FROM items WHERE id = ?", (item_id,))
                    title = item["title"] if item else "item"
                    gid = item["group_id"] if item else None
                    log_activity(conn, f"{current_user['name']} removed: {title}", "item_deleted", current_user["id"], gid)

                broadcast_event("state_updated", {
                    "action": "item_deleted",
                    "title": title,
                    "actor": current_user["name"],
                    "actor_id": current_user["id"]
                })
                self.send_json({"success": True})
                return

            # 5. Add Supermarket Bill and Split (in Euro €)
            if path == "/api/bills":
                store_name = body.get("store_name", "").strip() or "Supermarket"
                total_amount = float(body.get("total_amount", 0.0))
                paid_by = int(body.get("paid_by") or current_user["id"])
                split_with = body.get("split_with", [])
                bill_date = body.get("bill_date", "").strip() or datetime.utcnow().strftime("%Y-%m-%d")
                notes = body.get("notes", "").strip()
                raw_gid = body.get("group_id")
                try:
                    group_id = int(raw_gid) if (raw_gid is not None and int(raw_gid) > 0) else None
                except (ValueError, TypeError):
                    group_id = None

                if total_amount <= 0:
                    self.send_error_json("Total amount must be greater than 0")
                    return
                if not split_with:
                    self.send_error_json("Must select at least one person to split with")
                    return

                share = round(total_amount / len(split_with), 2)
                rounding_diff = round(total_amount - (share * len(split_with)), 2)

                with conn:
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO bills (store_name, total_amount, paid_by, bill_date, notes, group_id) VALUES (?, ?, ?, ?, ?, ?)",
                        (store_name, total_amount, paid_by, bill_date, notes, group_id)
                    )
                    bill_id = cur.lastrowid

                    for idx, mid in enumerate(split_with):
                        member_share = share + (rounding_diff if idx == 0 else 0.0)
                        cur.execute(
                            "INSERT INTO bill_splits (bill_id, member_id, share_amount) VALUES (?, ?, ?)",
                            (bill_id, mid, member_share)
                        )

                    payer = cur.execute("SELECT name FROM members WHERE id = ?", (paid_by,)).fetchone()
                    payer_name = payer["name"] if payer else current_user["name"]

                    log_activity(
                        conn,
                        f"{current_user['name']} added €{total_amount:.2f} bill for {store_name}",
                        "bill_added",
                        current_user["id"],
                        group_id
                    )

                broadcast_event("state_updated", {
                    "action": "bill_added",
                    "store": store_name,
                    "amount": total_amount,
                    "payer": payer_name,
                    "actor": current_user["name"],
                    "actor_id": current_user["id"]
                })
                self.send_json({"success": True, "bill_id": bill_id})
                return

            # 6. Settle Debt Between Friends (in Euro €)
            if path == "/api/settlements":
                from_id = current_user["id"]
                to_id = int(body.get("to_id", 0))
                amount = float(body.get("amount", 0.0))
                note = body.get("note", "").strip() or "Debt settlement"
                raw_gid = body.get("group_id")
                try:
                    group_id = int(raw_gid) if (raw_gid is not None and int(raw_gid) > 0) else None
                except (ValueError, TypeError):
                    group_id = None

                if not to_id or from_id == to_id:
                    self.send_error_json("Valid recipient is required")
                    return
                if amount <= 0:
                    self.send_error_json("Amount must be greater than 0")
                    return

                with conn:
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO settlements (from_member_id, to_member_id, amount, note, group_id) VALUES (?, ?, ?, ?, ?)",
                        (from_id, to_id, amount, note, group_id)
                    )
                    to_m = cur.execute("SELECT name FROM members WHERE id = ?", (to_id,)).fetchone()
                    to_name = to_m["name"] if to_m else "Friend"

                    log_activity(
                        conn,
                        f"{current_user['name']} paid €{amount:.2f} to {to_name}",
                        "settlement_recorded",
                        from_id,
                        group_id
                    )

                broadcast_event("state_updated", {
                    "action": "settlement",
                    "from": current_user["name"],
                    "to": to_name,
                    "amount": amount,
                    "actor": current_user["name"],
                    "actor_id": current_user["id"]
                })
                self.send_json({"success": True})
                return

            # 7. Admin Member Removal (Safely cascades dependencies)
            if path == "/api/members/remove":
                if not current_user.get("is_admin"):
                    self.send_error_json("Only Group Admin can remove members", status=403)
                    return

                target_id = int(body.get("member_id", 0))
                if target_id == current_user["id"]:
                    self.send_error_json("Admin cannot remove their own account")
                    return

                with conn:
                    cur = conn.cursor()
                    target = cur.execute("SELECT name, username FROM members WHERE id = ?", (target_id,)).fetchone()
                    if not target:
                        self.send_error_json("Member not found", status=404)
                        return

                    # Prevent removing the permanent admin
                    if is_permanent_admin(target["username"]):
                        self.send_error_json("Cannot remove the permanent admin account.")
                        return

                    target_name = target["name"]

                    # Clean all foreign-key dependent references safely before deleting
                    cur.execute("DELETE FROM sessions WHERE member_id = ?", (target_id,))
                    cur.execute("DELETE FROM bill_splits WHERE member_id = ?", (target_id,))
                    cur.execute("UPDATE items SET added_by = NULL WHERE added_by = ?", (target_id,))
                    cur.execute("UPDATE items SET bought_by = NULL WHERE bought_by = ?", (target_id,))
                    cur.execute("UPDATE activities SET member_id = NULL WHERE member_id = ?", (target_id,))
                    cur.execute("DELETE FROM settlements WHERE from_member_id = ? OR to_member_id = ?", (target_id, target_id))
                    cur.execute("DELETE FROM bills WHERE paid_by = ?", (target_id,))
                    cur.execute("DELETE FROM group_members WHERE member_id = ?", (target_id,))
                    cur.execute("DELETE FROM members WHERE id = ?", (target_id,))

                    log_activity(conn, f"Admin removed user: {target_name}", "member_removed", current_user["id"])

                broadcast_event("state_updated", {"action": "member_removed", "name": target_name})
                self.send_json({"success": True})
                return

            self.send_error_json("Endpoint not found", status=404)
        finally:
            conn.close()

def get_local_ip():
    """Detect local LAN IP for easy mobile Wi-Fi connection."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def run_server(port=8000):
    init_db()
    server_address = ("0.0.0.0", port)
    httpd = ThreadingHTTPServer(server_address, SPLITKARTRequestHandler)
    local_ip = get_local_ip()

    print("=" * 65)
    print(" 🛒 SPLITKART - Groups + Permanent Admin Active")
    print("=" * 65)
    print(f" ▸ Local Access:       http://localhost:{port}")
    print(f" ▸ Phone / Wi-Fi URL:  http://{local_ip}:{port}")
    print(f" ▸ Permanent Admin:    {PERMANENT_ADMIN_EMAIL}")
    print("=" * 65)
    print(" Sessions: Permanent HMAC Tokens | Groups System Active")
    print("=" * 65)
    sys.stdout.flush()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping SPLITKART server...")
        httpd.server_close()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run_server(port)
