# 🛒 SPLITKART — Shared Grocery Shopping & Group Bill Split (€)

[![Live Web App](https://img.shields.io/badge/Live%20App-grocery--split.onrender.com-059669?style=for-the-badge&logo=render)](https://grocery-split.onrender.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)
[![PWA Ready](https://img.shields.io/badge/PWA-Installable-purple?style=for-the-badge&logo=pwa)](https://grocery-split.onrender.com/)

A fast, real-time collaborative grocery shopping checklist and group expense splitting web application in Euros (**€**). Built with pure Python, SQLite, and modern responsive web technologies.

🔗 **Live Deployment:** [https://grocery-split.onrender.com/](https://grocery-split.onrender.com/)

---

## ✨ Key Features

### 👥 1. Multi-Group Isolation System (No Cross-Group Conflicts)
- **Separate Spaces:** Create or join isolated groups (e.g., Roommates, Family, Vacation Trip). Each group has its own grocery list, purchase history, bills, and balances.
- **8-Character Invite Codes:** Each group generates an 8-character code (e.g. `6TPX7SVL`). Friends simply enter this code to join.
- **1-Tap Group Switching:** Effortlessly switch between groups right from the top header or the Friends tab.
- **Personal List (No Group):** Use the app individually without a group whenever you want.

### 👑 2. Permanent Admin & Email Authentication
- **Locked Admin Rights:** The administrator account (`amarjithp45@gmail.com`) is permanently locked as Group Admin across all database resets and server reboots.
- **Email-Based Accounts:** All members register with a valid email address as their login identity.
- **Permanent Sessions:** Salted SHA-256 passwords + HMAC-signed tokens guarantee you remain logged in indefinitely across phone reboots and server spin-downs.

### 🛒 3. Real-Time Shared Grocery Checklist
- **Add Items with Quantities & Categories:** Produce, Dairy, Bakery, Pantry, Snacks, Drinks, Meat, etc.
- **Exact Timestamps:** Records exact date & time when each item was added and when it was purchased.
- **Update Quantity on Purchase:** When ticking an item off, a prompt lets the buyer confirm or update the exact quantity actually purchased (e.g., `2 packs`, `500g`).
- **Live Sync:** Instant real-time updates across all members via Server-Sent Events (SSE).

### 💶 4. Euro (€) Bill Splitting & Debt Simplification
- **Equal Bill Splits:** Log supermarket trips (Lidl, Aldi, SPAR, Carrefour, etc.) and pick which group members share the bill.
- **Smart Debt Minimization:** Automatically calculates net balances and simplifies debts (*"Alex pays Sam €14.50"*).
- **1-Tap Settle Up:** Record cash/Revolut/PayPal debt payments with immediate balance recalculation.

### 🔔 5. Mobile System Status Bar Notifications & PWA
- **Status Bar Alerts:** Real phone alerts via Service Worker `showNotification` with vibration when group members add or buy items.
- **Installable PWA:** Install directly to your Android or iPhone home screen with standalone app window and offline caching.

---

## 🚀 Quick Start (Local Setup)

SPLITKART runs with **zero third-party dependencies** (uses standard library Python 3):

```bash
# Clone the repository
git clone https://github.com/Amarjithp45/grocery-split.git
cd grocery-split

# Run the server
python server.py
```

Then open your browser:
- **Local Access:** `http://localhost:8000`
- **Phone / Wi-Fi Access:** `http://<your-local-ip>:8000`

---

## 🛠️ Architecture & Tech Stack

- **Backend:** Python 3 (`http.server.ThreadingHTTPServer` + `sqlite3`)
- **Real-Time Engine:** Server-Sent Events (SSE) `/api/events`
- **Security:** Salted SHA-256 password hashing + HMAC-SHA256 signed session tokens
- **Frontend:** Vanilla JavaScript (ES6+), Tailwind CSS, Web Audio API synthesis
- **PWA:** Service Worker (`sw.js`) with network-first strategy, Web App Manifest
- **Hosting:** Render (`https://grocery-split.onrender.com/`)

---

## 👤 Admin Access

- **Admin Email:** `amarjithp45@gmail.com`
- **Role:** Permanent Group Admin (can manage members and groups)
