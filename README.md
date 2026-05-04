# ⚽ World Cup 2026 Discord Bot

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![discord.py](https://img.shields.io/badge/discord.py-2.3.2-blueviolet.svg)](https://discordpy.readthedocs.io/en/stable/)
[![Flask](https://img.shields.io/badge/flask-2.x-lightgrey.svg)](https://flask.palletsprojects.com/)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-red.svg)](https://www.raspberrypi.com/)
[![License](https://img.shields.io/badge/license-private-orange.svg)](#)

A custom **Discord bot** for running a FIFA World Cup 2026 themed tournament server. It handles **team assignments, split ownership, betting, verification, backups, and tournament channel management**, with JSON storage and a **Flask web-based admin panel** for operations.

---

## ✨ What’s Included

### Discord Bot
- **Cog hot-reload** (`wc load`, `wc unload`, `wc reload`).
- **Guild tracking** stored in `JSON/guilds.json`.
- In-Discord **restart/stop** operations for admins.

### Tournament & Community Tools
- `/addplayer` - Assigns a random team to a player.
- `/reveal` - Reveals assigned teams to all players.
- `/split` - Requests split ownership of a team.
- `/makebet` - Creates and claims bets between players.
- Automated **entries tracker** embed.
- Role-based restrictions (`Root`, `Referee`, `Player`, `Spectator`).

### Verification
- `/verify` - Habbo-based verification system.
- Reaction-based role assignment for unverified users.

### Admin & Safety
- **Guild lock** - Leaves unauthorized servers automatically.
- **Message delete/purge** commands for cleanup.
- **Rules command** - Posts server rules in multiple messages.
- **Cog status tracking** with JSON sync.

### Backup & Restore
- Manual backup/restore commands.
- Retains up to 24 recent backup files.

### Web Admin Panel
Accessible via the Flask dashboard (default: `http://localhost:5000`):
- Start, stop, restart bot.
- View live **system & bot resource usage**.
- Monitor uptime & logs (`WC.log`, `health.log`).
- Manage **cogs** (reload/unload/load).
- Manage **bets** and settle outcomes.
- View/update **team ownerships**.
- Handle **split ownership** requests.
- Browse and download **JSON backups**.

---

## 📂 Repository Layout

```
WorldCupDiscBot/
├── README.md
├── LICENSE
├── updater.sh
└── WorldCupBot/
    ├── bot.py               # Main Discord bot
    ├── launcher.py          # Flask admin launcher
    ├── requirements.txt     # Python dependencies
    ├── routes_admin.py      # Admin panel routes
    ├── routes_public.py     # Public routes (if enabled)
    ├── stage_constants.py   # Tournament constants
    ├── COGS/                # Modular bot features
    ├── JSON/                # Data storage (players, teams, bets, etc.)
    ├── BACKUPS/             # Dedicated JSON backup archives
    └── static/              # Web panel frontend (index.html, style.css, app.js)
```

---

## 🛠️ Installation

### Requirements
- Python 3.10+
- A Discord Bot Token
- A Raspberry Pi (preferred deployment)

### Setup
```bash
# Clone repo
git clone https://github.com/yourusername/WorldCupDiscBot.git
cd WorldCupDiscBot

# Create virtual environment
python3 -m venv WCenv
source WCenv/bin/activate

# Install dependencies
pip install -r WorldCupBot/requirements.txt

# Start launcher (Flask panel + bot)
python WorldCupBot/launcher.py
```

---

## 🔑 Configuration

1. **Discord token**: add your bot token in `WorldCupBot/bot.py` (never commit real tokens).
2. **Guild/role/channel IDs**: update the relevant values inside the `COGS/` files.
3. **Data storage**: JSON files under `WorldCupBot/JSON/` are the main data store. Avoid manual edits unless necessary.

---

## ▶️ Usage

- Manage the bot from **Discord commands** or the **web admin panel**.
- Logs are written to `WorldCupBot/WC.log` and `WorldCupBot/health.log`.
- Backups run automatically every hour (when enabled) and are also available manually via the admin panel.

---

## ✅ Testing & Load Harness

### Automated tests (pytest)
```bash
pip install -r requirements-dev.txt
pytest
```

### Load testing the Flask API
```bash
python scripts/load_test.py --base-url http://localhost:5000 --duration 60 --concurrency 20
```

### Offline UI behavior
The web panel now supports **offline mode** when the bot or API is unavailable. It will:
- Show a banner when the bot is offline or the panel loses connection.
- Render cached dashboard data while offline.
- Display a short “syncing” indicator when the bot reconnects.

--- 

## 📸 Screenshot

If you want a preview on GitHub, place the admin panel screenshot at:

```
WorldCupBot/static/preview.png
```

Then reference it in the README like this:

```md
![Admin Panel Dashboard](WorldCupBot/static/preview.png)
```

---

## 📜 License

This project is private and tailored for **World Cup 2026 community events**.
Not intended for public redistribution without permission.
