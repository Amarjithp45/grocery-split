#!/usr/bin/env python3
"""
CartShare - Collaborative Grocery Shopping & Bill-Splitting Server
A zero-dependency Python 3 server with SQLite persistence, REST API,
and real-time Server-Sent Events (SSE) synchronization.
"""

import os
import sys
import json
import sqlite3
import socket
import threading
import queue
import mimetypes
from datetime import datetime
from urllib.parse import urlparse, parse_qs
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

def get_db():
    """Get a thread-local SQLite connection with dictionary-like row access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    """Initialize database tables and seed starter members if empty."""
    conn = get_db()
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                avatar_color TEXT NOT NULL DEFAULT '#10b981',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

        # Seed sample members if fresh
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS cnt FROM members")
        if cur.fetchone()["cnt"] == 0:
            sample_members = [
                ("Alex", "#3b82f6"),
                ("Sam", "#10b981"),
                ("Taylor", "#f59e0b"),
                ("Jordan", "#8b5cf6")
            ]
            for name, color in sample_members:
                conn.execute("INSERT INTO members (name, avatar_color) VALUES (?, ?)", (name, color))

            sample_items = [
                ("Organic Whole Milk", "2 cartons", "Dairy", 1, 1),
                ("Avocados", "4 pcs", "Produce", 0, 2),
                ("Sourdough Bread", "1 loaf", "Bakery", 1, 3),
                ("Eggs (Large Brown)", "1 dozen", "Dairy", 0, 1),
                ("Cold Brew Coffee", "2 bottles", "Drinks", 0, 4)
            ]
            for title, qty, cat, urgent, added_by in sample_items:
                conn.execute(
                    "INSERT INTO items (title, quantity, category, is_urgent, added_by) VALUES (?, ?, ?, ?, ?)",
                    (title, qty, cat, urgent, added_by)
                )

            conn.execute(
                "INSERT INTO activities (message, action_type, member_id) VALUES (?, ?, ?)",
                ("CartShare group created with starter grocery list", "system", 1)
            )
    conn.close()

def log_activity(conn, message: str, action_type: str, member_id=None):
    """Record an action in the activity log."""
    conn.execute(
        "INSERT INTO activities (message, action_type, member_id) VALUES (?, ?, ?)",
        (message, action_type, member_id)
    )

def calculate_debt_transfers(members, net_balances):
    """
    Minimizes debt transfers between members using greedy reconciliation.
    net_balances: {member_id: float (positive = owed money, negative = owes money)}
    Returns list of dicts: [{from_id, from_name, to_id, to_name, amount}]
    """
    name_map = {m["id"]: m["name"] for m in members}
    debtors = []   # owes money (negative balance)
    creditors = [] # owed money (positive balance)

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

def get_full_state():
    """Retrieve full application state for client consumption."""
    conn = get_db()
    try:
        members = [dict(r) for r in conn.execute("SELECT * FROM members ORDER BY name ASC").fetchall()]
        
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
        # balance[m] = (total paid in bills + payments made in settlements)
        #            - (total share owed in bills + settlements received)
        net_balances = {m["id"]: 0.0 for m in members}
        
        # Credit whoever paid the bill
        for b in bills:
            net_balances[b["paid_by"]] = net_balances.get(b["paid_by"], 0.0) + b["total_amount"]
            for s in b["splits"]:
                net_balances[s["member_id"]] = net_balances.get(s["member_id"], 0.0) - s["share_amount"]

        # Factor in settlements
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
        # Enable CORS for local testing/multi-device
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
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
            state = get_full_state()
            self.send_json(state)
            return

        if path == "/api/events":
            # Server-Sent Events stream for real-time updates
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
                # Send initial ping
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                while True:
                    try:
                        msg = q.get(timeout=20.0)
                        self.wfile.write(msg.encode("utf-8"))
                        self.wfile.flush()
                    except queue.Empty:
                        # Keep-alive heartbeat
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

        # Prevent directory traversal
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
            # 1. Add New Member
            if path == "/api/members":
                name = body.get("name", "").strip()
                color = body.get("avatar_color", "#10b981")
                if not name:
                    self.send_error_json("Member name is required")
                    return
                try:
                    with conn:
                        cur = conn.cursor()
                        cur.execute("INSERT INTO members (name, avatar_color) VALUES (?, ?)", (name, color))
                        member_id = cur.lastrowid
                        log_activity(conn, f"Joined the group: {name}", "member_joined", member_id)
                    broadcast_event("state_updated", {"action": "member_added", "member": name})
                    self.send_json({"success": True, "id": member_id, "name": name})
                except sqlite3.IntegrityError:
                    self.send_error_json(f"A member named '{name}' already exists.")
                return

            # 2. Add Grocery Item
            if path == "/api/items":
                title = body.get("title", "").strip()
                quantity = body.get("quantity", "1").strip() or "1"
                category = body.get("category", "Pantry").strip() or "Pantry"
                is_urgent = 1 if body.get("is_urgent") else 0
                added_by = body.get("added_by")

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

                    adder_name = "Someone"
                    if added_by:
                        m = conn.execute("SELECT name FROM members WHERE id = ?", (added_by,)).fetchone()
                        if m:
                            adder_name = m["name"]

                    log_activity(conn, f"{adder_name} added: {title} ({quantity})", "item_added", added_by)

                broadcast_event("state_updated", {
                    "action": "item_added",
                    "title": title,
                    "added_by": adder_name
                })
                self.send_json({"success": True, "id": item_id})
                return

            # 3. Toggle Item Bought Status
            if path == "/api/items/toggle":
                item_id = body.get("item_id")
                member_id = body.get("member_id")

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
                    bought_by = member_id if new_status == 1 else None
                    bought_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") if new_status == 1 else None

                    cur.execute(
                        "UPDATE items SET is_bought = ?, bought_by = ?, bought_at = ? WHERE id = ?",
                        (new_status, bought_by, bought_at, item_id)
                    )

                    actor_name = "Someone"
                    if member_id:
                        m = cur.execute("SELECT name FROM members WHERE id = ?", (member_id,)).fetchone()
                        if m:
                            actor_name = m["name"]

                    msg = f"{actor_name} bought: {item['title']}" if new_status else f"{actor_name} moved back to cart: {item['title']}"
                    log_activity(conn, msg, "item_toggled", member_id)

                broadcast_event("state_updated", {
                    "action": "item_toggled",
                    "title": item["title"],
                    "is_bought": bool(new_status),
                    "actor": actor_name
                })
                self.send_json({"success": True, "is_bought": bool(new_status)})
                return

            # 4. Clear All Bought Items
            if path == "/api/items/clear-bought":
                member_id = body.get("member_id")
                with conn:
                    cur = conn.cursor()
                    count = cur.execute("SELECT COUNT(*) AS cnt FROM items WHERE is_bought = 1").fetchone()["cnt"]
                    cur.execute("DELETE FROM items WHERE is_bought = 1")
                    
                    actor_name = "Someone"
                    if member_id:
                        m = cur.execute("SELECT name FROM members WHERE id = ?", (member_id,)).fetchone()
                        if m:
                            actor_name = m["name"]
                    
                    log_activity(conn, f"{actor_name} cleared {count} purchased item(s)", "cleared_bought", member_id)

                broadcast_event("state_updated", {"action": "cleared_bought", "count": count, "actor": actor_name})
                self.send_json({"success": True, "cleared_count": count})
                return

            # 5. Delete Item
            if path == "/api/items/delete":
                item_id = body.get("item_id")
                member_id = body.get("member_id")
                if not item_id:
                    self.send_error_json("item_id is required")
                    return
                with conn:
                    cur = conn.cursor()
                    item = cur.execute("SELECT title FROM items WHERE id = ?", (item_id,)).fetchone()
                    cur.execute("DELETE FROM items WHERE id = ?", (item_id,))
                    actor_name = "Someone"
                    if member_id:
                        m = cur.execute("SELECT name FROM members WHERE id = ?", (member_id,)).fetchone()
                        if m:
                            actor_name = m["name"]
                    title = item["title"] if item else "item"
                    log_activity(conn, f"{actor_name} removed: {title}", "item_deleted", member_id)

                broadcast_event("state_updated", {"action": "item_deleted", "title": title})
                self.send_json({"success": True})
                return

            # 6. Add Supermarket Bill and Split
            if path == "/api/bills":
                store_name = body.get("store_name", "").strip() or "Supermarket"
                total_amount = float(body.get("total_amount", 0.0))
                paid_by = body.get("paid_by")
                split_with = body.get("split_with", []) # list of member_ids
                bill_date = body.get("bill_date", "").strip() or datetime.utcnow().strftime("%Y-%m-%d")
                notes = body.get("notes", "").strip()

                if total_amount <= 0:
                    self.send_error_json("Total amount must be greater than 0")
                    return
                if not paid_by:
                    self.send_error_json("Payer must be specified")
                    return
                if not split_with:
                    self.send_error_json("Must select at least one person to split with")
                    return

                share = round(total_amount / len(split_with), 2)
                # Adjust rounding discrepancy on first person
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
                    payer_name = payer["name"] if payer else "Someone"

                    log_activity(
                        conn, 
                        f"{payer_name} added a ${total_amount:.2f} bill for {store_name} (split among {len(split_with)} friends)",
                        "bill_added", 
                        paid_by
                    )

                broadcast_event("state_updated", {
                    "action": "bill_added",
                    "store": store_name,
                    "amount": total_amount,
                    "payer": payer_name
                })
                self.send_json({"success": True, "bill_id": bill_id})
                return

            # 7. Settle Debt Between Friends
            if path == "/api/settlements":
                from_id = body.get("from_id")
                to_id = body.get("to_id")
                amount = float(body.get("amount", 0.0))
                note = body.get("note", "").strip() or "Debt settlement"

                if not from_id or not to_id or from_id == to_id:
                    self.send_error_json("Valid payer and recipient are required")
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
                    
                    from_m = cur.execute("SELECT name FROM members WHERE id = ?", (from_id,)).fetchone()
                    to_m = cur.execute("SELECT name FROM members WHERE id = ?", (to_id,)).fetchone()
                    from_name = from_m["name"] if from_m else "User"
                    to_name = to_m["name"] if to_m else "User"

                    log_activity(
                        conn,
                        f"{from_name} paid ${amount:.2f} to {to_name} (Settled)",
                        "settlement_recorded",
                        from_id
                    )

                broadcast_event("state_updated", {
                    "action": "settlement",
                    "from": from_name,
                    "to": to_name,
                    "amount": amount
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
        # Dummy connect to public DNS to find outbound interface
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
    print(" Real-time sync & notifications active! Press Ctrl+C to stop.")
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
