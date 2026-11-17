# 🛒 CartShare — Group Grocery List & Bill Splitting

A modern, real-time web application built for friends, roommates, and family to collaborate on grocery shopping lists, track supermarket purchases, and split bills seamlessly.

---

## ✨ Features

- **🛒 Real-Time Grocery Checklist:** Add items with quantities, aisle categories (*Produce, Dairy, Pantry, Bakery, etc.*), and priority flags.
- **⚡ Instant Real-Time Synchronization:** Uses Server-Sent Events (SSE) so whenever any friend adds, buys, or deletes an item on their phone or computer, everyone's screen updates instantly.
- **✓ 1-Tap Purchase & Clean Up:** Check items off right in the supermarket aisle. Bought items move into a "Purchased Items" tray with timestamps and who bought them, with a 1-click "Clear Purchased" button.
- **🧾 Bill & Expense Splitting (Splitwise-style):**
  - Record supermarket receipts with total amount, who paid, and which friends are splitting the bill.
  - Automatically calculates net balances and minimizes debt transfers (e.g. *"Sarah owes Alex \$18.50"*).
  - 1-click **"Settle Up"** button to log repayments.
- **🔔 Live Notifications & Audio Cues:**
  - Browser Push Notifications (via Web Notification API) when someone adds an item or records a bill.
  - Synthesized audio feedback (Web Audio API) when items are checked off or settled.
  - Live activity feed showing the history of actions.
- **📱 Mobile-First Supermarket Mode:** Optimized for thumb navigation on mobile phones while walking store aisles.
- **🔒 Zero-Dependency Python Architecture:** Runs directly with Python 3 and SQLite without needing Node.js, npm, or external pip packages!

---

## 🚀 Quick Start (Running Locally)

### 1. Start the Server
Open PowerShell or Command Prompt, navigate to the folder, and run:
```bash
python server.py
```

You'll see:
```text
=================================================================
 🛒 CartShare - Group Grocery & Bill-Splitting Website
=================================================================
 ▸ Local Access:       http://localhost:8000
 ▸ Phone / Wi-Fi URL:  http://192.168.1.xxx:8000
=================================================================
 Real-time sync & notifications active! Press Ctrl+C to stop.
=================================================================
```

### 2. Open on Your Devices
- **On your computer:** Open `http://localhost:8000` in your web browser.
- **On your friends' phones:** Make sure everyone is connected to the same Wi-Fi network, and open the `http://<YOUR_IP>:8000` link on mobile browsers (Safari, Chrome, etc.).

---

## 📂 Project Structure

```text
grocery-split/
├── server.py             # Threading Python HTTP Server, SQLite DB & SSE Hub
├── grocery.db            # Persistent SQLite database (auto-generated)
├── static/
│   ├── index.html        # Responsive UI (Tailwind CSS, Lucide icons)
│   ├── app.js            # Client logic, SSE listener, Web Audio synth, Modals
│   └── style.css         # Custom animations, checkbox styles & category badges
└── README.md             # Project documentation
```

---

## 🌐 Deploying Online (Free Hosting Options)

To let friends access the website when they are not on your home Wi-Fi:

### Option A: Render.com (Recommended - 100% Free)
1. Push this folder to a GitHub repository.
2. In [Render.com](https://render.com), click **New + Web Service**.
3. Select your GitHub repository.
4. Set:
   - **Environment:** `Python 3`
   - **Build Command:** *(leave empty or `echo "Ready"`)*
   - **Start Command:** `python server.py $PORT`
5. Click **Deploy**! Render will give you a public URL (e.g., `https://cartshare.onrender.com`).

### Option B: PythonAnywhere (Free)
1. Upload `server.py` and the `static/` directory to PythonAnywhere.
2. Set up a Web App pointing to `server.py`.

---

## 💡 Tech Highlights
- **Backend:** Python 3 standard library `http.server.ThreadingHTTPServer` + `sqlite3`.
- **Real-Time Push:** Server-Sent Events (SSE) `/api/events` with concurrent subscriber queues.
- **Audio:** Web Audio API sound synthesis (zero audio asset dependencies).
- **Frontend:** Responsive HTML5 + Tailwind CSS CDN + vanilla modern JavaScript.
