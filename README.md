# ⚽ World Cup 2026 Discord Bot  

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)  
[![discord.py](https://img.shields.io/badge/discord.py-2.3.2-blueviolet.svg)](https://discordpy.readthedocs.io/en/stable/)  
[![Flask](https://img.shields.io/badge/flask-2.x-lightgrey.svg)](https://flask.palletsprojects.com/)  
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-red.svg)](https://www.raspberrypi.com/)  
[![License](https://img.shields.io/badge/license-private-orange.svg)](#)  

A custom **Discord bot** built for managing a FIFA World Cup 2026 themed tournament server.  
It handles **team assignments, split ownership, betting, verification, backups, and tournament channel management** — all backed by JSON storage and managed via a **Flask web-based admin panel**.  

---

## 🚀 Features  

### Core Bot  
- Dynamic **cog loading/unloading/reloading** (`wc load`, `wc unload`, `wc reload`)  
- **Auto guild tracker** (updates `guilds.json`)  
- **Restart/Stop commands** directly from Discord  

### Tournament Tools  
- `/addplayer` - Assign random team to player  
- `/reveal` - Reveal teams to all players  
- `/split` - Request split ownership of a team  
- `/makebet` - Create and claim bets between players  
- Automated **entries tracker** embed  
- Role-based restrictions (`Root`, `Referee`, `Player`, `Spectator`)  

### Verification  
- `/verify` - Habbo-based verification system  
- Reaction-based role assignment for unverified users  

### Admin & Safety  
- **Guild lock** - Leaves unauthorized servers automatically  
- **Message delete/purge** commands for cleanup  
- **Rules command** - Posts server rules in multiple messages  
- **Cog status tracking** with JSON sync  

### Backup & Restore  
- Automatic JSON backups every 6 hours  
- Manual backup/restore commands  
- Retains up to 25 recent backup files  

### Web Admin Panel (`launcher.py`)  
Accessible via **Flask dashboard** (default: `http://localhost:5000`)  
- Start, stop, restart bot  
- View live **system & bot resource usage**  
- Monitor uptime & logs (`WC.log`, `health.log`)  
- Manage **cogs** (reload/unload/load) via webhooks  
- Manage **bets** and settle outcomes  
- View and update **team ownerships**  
- Handle **split ownership requests**  
- Browse and download **JSON backups**  

### Frontend (`index.html`, `style.css`, `app.js`)  
- Responsive web UI for the admin panel  
- Dark/Light theme toggle  
- Sections for Dashboard, Logs, Team Ownership, Bets, Cogs, Splits, Backups  

---

## 📂 Project Structure  

```
WorldCupDiscBot/
│── bot.py               # Main Discord bot
│── launcher.py          # Flask admin launcher
│── requirements.txt     # Python dependencies
│
├── COGS/                # Modular bot features
│   ├── AdminControl.py
│   ├── BackupRestore.py
│   ├── Betting.py
│   ├── BetAdminSettle.py
│   ├── ChannelManage.py
│   ├── EntriesTracker.py
│   ├── GuildLocker.py
│   ├── MessageDelete.py
│   ├── ReactionRole.py
│   ├── Rules.py
│   ├── SplitOwnership.py
│   ├── TeamsDistribution.py
│   ├── WCVerify.py
│   ├── nem.py
│   └── role_utils.py
│
├── JSON/                # Data storage (players, teams, bets, etc.)
├── Backups/             # JSON backups
├── static/              # Web panel frontend
│   ├── index.html
│   ├── style.css
│   └── app.js
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
pip install -r requirements.txt

# Start launcher (Flask panel + bot)
python launcher.py
```

---

## 🔑 Configuration  

- Place your **Discord bot token** inside `bot.py` (never commit real tokens to GitHub).  
- Edit cog files (`COGS/`) to adjust **guild IDs, role IDs, channel IDs** as needed.  
- JSON files under `/JSON` are the main data storage — do not edit manually unless necessary.  

---

## 🖥️ Usage  

- Manage bot entirely from **Discord commands** or via the **web admin panel**.  
- Logs are written to `WC.log` and `health.log`.  
- Backups are automatically created every 6 hours.  

---

## 📸 Preview Screenshot  

Here’s a preview of the **Admin Panel Dashboard**:  

![Admin Panel Dashboard](static/preview.png)  

*(Place your screenshot as `static/preview.png` so it loads correctly on GitHub)*  

---

## 📜 License  

This project is private and tailored for **World Cup 2026 community events**.  
Not intended for public redistribution without permission.  
