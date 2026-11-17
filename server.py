#!/usr/bin/env python3
"""
CartShare - Collaborative Grocery Shopping & Bill-Splitting Server
Features:
- User Registration & Authentication (hashed passwords + session tokens)
- Identity locking (users can only act as themselves)
- SQLite database persistence with foreign keys
- Server-Sent Events (SSE) for instant push updates
- REST API for items, bills, debts, and settlements
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
import secrets
from datetime import datetime
from urllib.parse import urlparse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# Base paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DB_PATH = os.path.join(BASE_DIR, "grocery.db")

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

def get_db():
    """Get a thread-local SQLite connection with dictionary-like row access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    """Initialize database tables, ensure auth schema, and create sessions table."""
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration: Add username/password/salt columns if missing from earlier runs
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(members)")
        cols = [r["name"] for r in cur.fetchall()]
        if "username" not in cols:
            conn.execute("ALTER TABLE members ADD COLUMN username TEXT")
        if "password_hash" not in cols:
            conn.execute("ALTER TABLE members ADD COLUMN password_hash TEXT")
        if "salt" not in cols:
            conn.execute("ALTER TABLE members ADD COLUMN salt TEXT")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                member_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (member_id) REFERENCES members(id)
            )
        """)

        # If fresh database, seed sample items
        cur.execute("SELECT COUNT(*) AS cnt FROM items")
        if cur.fetchone()["cnt"] == 0:
            sample_items = [
                ("Organic Whole Milk", "2 cartons", "Dairy", 1, None),
                ("Avocados", "4 pcs", "Produce", 0, None),
                ("Sourdough Bread", "1 loaf", "Bakery", 1, None),
                ("Eggs (Large Brown)", "1 dozen", "Dairy", 0, None),
                ("Cold Brew Coffee", "2 bottles", "Drinks", 0, None)
            ]
            for title, qty, cat, urgent, added_by in sample_items:
                conn.execute(
                    "INSERT INTO items (title, quantity, category, is_urgent, added_by) VALUES (?, ?, ?, ?, ?)",
                    (title, qty, cat, urgent, added_by)
                )
    conn.close()

def log_activity(conn, message: str, action_type: str, member_id=None):
    """Record an action in the activity log."""
    conn.execute(
        "INSERT INTO activities (message, action_type, member_id) VALUES (?, ?, ?)",
        (message, action_type, member_id)
    )

def get_authenticated_member(headers):
    """Identify the logged-in member from the Authorization header or session cookie."""
    auth_header = headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    if not token:
        cookie_header = headers.get("Cookie", "")
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith("session_token="):
                token = part.split("=")[1].strip()
                break
    if not token:
        return None

    conn = get_db()
    try:
        row = conn.execute("""
            SELECT m.id, m.name, m.username, m.avatar_color
            FROM sessions s
            JOIN members m ON s.member_id = m.id
            WHERE s.token = ?
        """, (token,)).fetchone()
        return dict(row) if row else None
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

def get_full_state(current_user=None):
    """Retrieve full application state for client consumption."""
    conn = get_db()
    try:
        # Public member roster (name, avatar, id - no password/salt)
        members = [
            {"id": r["id"], "name": r["name"], "avatar_color": r["avatar_color"]}
            for r in conn.execute("SELECT id, name, avatar_color FROM members ORDER BY name ASC").fetchall()
        ]
        
        items_query = """
            SELECT i.*, 
                   m1.name AS added_by_name, m1.avatar_color AS added_by_color,
                   m2.name AS bought_by_name, m2.avatar_color AS bought_by_color
            FROM items i
            LEFT JOIN members m1 ON i.added_by = m1.id
            LEFT JOIN members m2 ON i.bought_by = m2.id
            ORDER BY i.is_urgent DESC, i.id DESC
        """
        all_items = [dict(r) for r in conn.execute(items_query).fetchall()]
        active_items = [i for i in all_items if not i["is_bought"]]
        bought_items = [i for i in all_items if i["is_bought"]]

        # Bills with splits
        bills_rows = conn.execute("""
            SELECT b.*, m.name AS paid_by_name, m.avatar_color AS paid_by_color
            FROM bills b
            JOIN members m ON b.paid_by = m.id
            ORDER BY b.bill_date DESC, b.id DESC
        """).fetchall()

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

        # Settlements
        settlements = [dict(r) for r in conn.execute("""
            SELECT s.*, 
                   m1.name AS from_name, m1.avatar_color AS from_color,
                   m2.name AS to_name, m2.avatar_color AS to_color
            FROM settlements s
            JOIN members m1 ON s.from_member_id = m1.id
            JOIN members m2 ON s.to_member_id = m2.id
            ORDER BY s.id DESC
            LIMIT 50
        """).fetchall()]

        # Net balance calculation
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
            ORDER BY a.id DESC
            LIMIT 60
        """).fetchall()]

        total_spent = sum(b["total_amount"] for b in bills)

        return {
            "currentUser": current_user,
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
                "total_spent": round(total_spent, 2)
            }
        }
    finally:
        conn.close()

class CartShareRequestHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
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

        if path == "/api/state":
            current_user = get_authenticated_member(self.headers)
            state = get_full_state(current_user)
            self.send_json(state)
            return

        if path == "/api/auth/me":
            user = get_authenticated_member(self.headers)
            if user:
                self.send_json({"authenticated": True, "user": user})
            else:
                self.send_json({"authenticated": False})
            return

        if path == "/api/events":
            # Server-Sent Events stream for real-time mobile push
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
            # -----------------------------------------------------
            # AUTH: Register New Friend
            # -----------------------------------------------------
            if path == "/api/auth/register":
                username = body.get("username", "").strip().lower()
                password = body.get("password", "").strip()
                name = body.get("name", "").strip()

                if not username or len(username) < 3:
                    self.send_error_json("Username must be at least 3 characters")
                    return
                if not password or len(password) < 4:
                    self.send_error_json("Password must be at least 4 characters")
                    return
                if not name:
                    name = username.capitalize()

                colors = ['#10b981', '#3b82f6', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316']
                avatar_color = colors[len(username) % len(colors)]

                hashed, salt = hash_password(password)

                try:
                    with conn:
                        cur = conn.cursor()
                        cur.execute(
                            "INSERT INTO members (name, username, password_hash, salt, avatar_color) VALUES (?, ?, ?, ?, ?)",
                            (name, username, hashed, salt, avatar_color)
                        )
                        member_id = cur.lastrowid
                        token = secrets.token_hex(32)
                        cur.execute("INSERT INTO sessions (token, member_id) VALUES (?, ?)", (token, member_id))
                        log_activity(conn, f"{name} registered and joined CartShare", "member_joined", member_id)

                    user_obj = {"id": member_id, "name": name, "username": username, "avatar_color": avatar_color}
                    broadcast_event("state_updated", {
                        "action": "member_joined",
                        "name": name,
                        "actor_id": member_id
                    })
                    self.send_json({"success": True, "token": token, "user": user_obj})
                except sqlite3.IntegrityError:
                    self.send_error_json("A user with that username or name already exists.")
                return

            # -----------------------------------------------------
            # AUTH: Login Existing Friend
            # -----------------------------------------------------
            if path == "/api/auth/login":
                username = body.get("username", "").strip().lower()
                password = body.get("password", "").strip()

                if not username or not password:
                    self.send_error_json("Username and password are required")
                    return

                cur = conn.cursor()
                row = cur.execute("SELECT * FROM members WHERE LOWER(username) = ? OR LOWER(name) = ?", (username, username)).fetchone()
                if not row or not row["password_hash"] or not row["salt"]:
                    self.send_error_json("Invalid username or password", status=401)
                    return

                check_hash, _ = hash_password(password, row["salt"])
                if check_hash != row["password_hash"]:
                    self.send_error_json("Invalid username or password", status=401)
                    return

                token = secrets.token_hex(32)
                with conn:
                    conn.execute("INSERT INTO sessions (token, member_id) VALUES (?, ?)", (token, row["id"]))

                user_obj = {
                    "id": row["id"],
                    "name": row["name"],
                    "username": row["username"],
                    "avatar_color": row["avatar_color"]
                }
                self.send_json({"success": True, "token": token, "user": user_obj})
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
            current_user = get_authenticated_member(self.headers)
            if not current_user:
                self.send_error_json("Authentication required. Please log in.", status=401)
                return

            # 1. Add Grocery Item (Identity locked to current_user)
            if path == "/api/items":
                title = body.get("title", "").strip()
                quantity = body.get("quantity", "1").strip() or "1"
                category = body.get("category", "Pantry").strip() or "Pantry"
                is_urgent = 1 if body.get("is_urgent") else 0
                added_by = current_user["id"]  # Strictly derived from session!

                if not title:
                    self.send_error_json("Item name is required")
                    return

                with conn:
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO items (title, quantity, category, is_urgent, added_by) VALUES (?, ?, ?, ?, ?)",
                        (title, quantity, category, is_urgent, added_by)
                    )
                    item_id = cur.lastrowid
                    log_activity(conn, f"{current_user['name']} added: {title} ({quantity})", "item_added", added_by)

                broadcast_event("state_updated", {
                    "action": "item_added",
                    "title": title,
                    "quantity": quantity,
                    "actor": current_user["name"],
                    "actor_id": current_user["id"]
                })
                self.send_json({"success": True, "id": item_id})
                return

            # 2. Toggle Item Bought Status (Identity locked to current_user)
            if path == "/api/items/toggle":
                item_id = body.get("item_id")
                if not item_id:
                    self.send_error_json("item_id is required")
                    return

                with conn:
                    cur = conn.cursor()
                    item = cur.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
                    if not item:
                        self.send_error_json("Item not found", status=404)
                        return

                    new_status = 0 if item["is_bought"] else 1
                    bought_by = current_user["id"] if new_status == 1 else None
                    bought_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") if new_status == 1 else None

                    cur.execute(
                        "UPDATE items SET is_bought = ?, bought_by = ?, bought_at = ? WHERE id = ?",
                        (new_status, bought_by, bought_at, item_id)
                    )

                    msg = (
                        f"{current_user['name']} bought: {item['title']}"
                        if new_status
                        else f"{current_user['name']} moved back to cart: {item['title']}"
                    )
                    log_activity(conn, msg, "item_toggled", current_user["id"])

                broadcast_event("state_updated", {
                    "action": "item_toggled",
                    "title": item["title"],
                    "is_bought": bool(new_status),
                    "actor": current_user["name"],
                    "actor_id": current_user["id"]
                })
                self.send_json({"success": True, "is_bought": bool(new_status)})
                return

            # 3. Clear All Bought Items
            if path == "/api/items/clear-bought":
                with conn:
                    cur = conn.cursor()
                    count = cur.execute("SELECT COUNT(*) AS cnt FROM items WHERE is_bought = 1").fetchone()["cnt"]
                    cur.execute("DELETE FROM items WHERE is_bought = 1")
                    log_activity(conn, f"{current_user['name']} cleared {count} purchased item(s)", "cleared_bought", current_user["id"])

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
                    item = cur.execute("SELECT title FROM items WHERE id = ?", (item_id,)).fetchone()
                    cur.execute("DELETE FROM items WHERE id = ?", (item_id,))
                    title = item["title"] if item else "item"
                    log_activity(conn, f"{current_user['name']} removed: {title}", "item_deleted", current_user["id"])

                broadcast_event("state_updated", {
                    "action": "item_deleted",
                    "title": title,
                    "actor": current_user["name"],
                    "actor_id": current_user["id"]
                })
                self.send_json({"success": True})
                return

            # 5. Add Supermarket Bill and Split
            if path == "/api/bills":
                store_name = body.get("store_name", "").strip() or "Supermarket"
                total_amount = float(body.get("total_amount", 0.0))
                paid_by = int(body.get("paid_by") or current_user["id"])
                split_with = body.get("split_with", [])
                bill_date = body.get("bill_date", "").strip() or datetime.utcnow().strftime("%Y-%m-%d")
                notes = body.get("notes", "").strip()

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
                        "INSERT INTO bills (store_name, total_amount, paid_by, bill_date, notes) VALUES (?, ?, ?, ?, ?)",
                        (store_name, total_amount, paid_by, bill_date, notes)
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
                        f"{current_user['name']} recorded a ${total_amount:.2f} bill for {store_name} (Paid by {payer_name})",
                        "bill_added", 
                        current_user["id"]
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

            # 6. Settle Debt Between Friends (from_id locked to current_user)
            if path == "/api/settlements":
                from_id = current_user["id"]  # You can only log debts you pay
                to_id = int(body.get("to_id", 0))
                amount = float(body.get("amount", 0.0))
                note = body.get("note", "").strip() or "Debt settlement"

                if not to_id or from_id == to_id:
                    self.send_error_json("Valid recipient is required")
                    return
                if amount <= 0:
                    self.send_error_json("Amount must be greater than 0")
                    return

                with conn:
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO settlements (from_member_id, to_member_id, amount, note) VALUES (?, ?, ?, ?)",
                        (from_id, to_id, amount, note)
                    )
                    to_m = cur.execute("SELECT name FROM members WHERE id = ?", (to_id,)).fetchone()
                    to_name = to_m["name"] if to_m else "Friend"

                    log_activity(
                        conn,
                        f"{current_user['name']} paid ${amount:.2f} to {to_name} (Settled)",
                        "settlement_recorded",
                        from_id
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
    httpd = ThreadingHTTPServer(server_address, CartShareRequestHandler)
    local_ip = get_local_ip()

    print("=" * 65)
    print(" 🛒 CartShare - Group Grocery & Bill-Splitting Website")
    print("=" * 65)
    print(f" ▸ Local Access:       http://localhost:{port}")
    print(f" ▸ Phone / Wi-Fi URL:  http://{local_ip}:{port}")
    print("=" * 65)
    print(" Auth security & mobile push notifications enabled!")
    print("=" * 65)
    sys.stdout.flush()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping CartShare server...")
        httpd.server_close()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run_server(port)
