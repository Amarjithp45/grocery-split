# 🛒 Palachrakk — Group Grocery List & Bill Splitting (€)

A modern, real-time web application built for friends, roommates, and family to collaborate on grocery shopping lists, track supermarket purchases, and split bills seamlessly in Euros (€).

---

## ✨ Features

- **🛒 Real-Time Grocery Checklist:** Add items with quantities, store categories (*Produce, Dairy, Pantry, Bakery, etc.*), and priority flags.
- **🕒 Date & Time Tracking:** Shows the exact date and time when every item was added to the list and when it was checked out/bought at the supermarket.
- **💶 Euro (€) Expense Splitting:**
  - Record supermarket bills in Euros (€), select who paid, and choose who splits it.
  - Automatically calculates net balances and minimizes debt transfers (e.g. *"Sam owes Alex €20.00"*).
  - 1-click **"Pay Back"** button to record settlements.
- **🔐 Secure User Registration & Log In:** Hashed passwords and secure session tokens with locked single-user identities.
- **🔔 Real Phone Notification Bar Alerts:**
  - Browser Push Notifications (via Service Worker) with vibration and sound when friends add or buy items.
  - Live activity feed and Web Audio chimes.
- **📱 Installable Mobile App (PWA):** Install directly to your phone's home screen via Chrome or Safari with 1 tap.
- **🔒 Zero-Dependency Python Architecture:** Runs directly with Python 3 and SQLite without needing Node.js, npm, or external pip packages!

---

## 🚀 Running Locally

```powershell
python server.py
```
Open `http://localhost:8000` on your computer or `http://192.168.x.x:8000` on your mobile phone connected to Wi-Fi.
