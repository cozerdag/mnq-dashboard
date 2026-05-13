# MNQ Bot Trading Dashboard — Setup Guide

## What You Get

- `index.html` — your trading dashboard (open in any browser)
- `scripts/update_dashboard.sh` — copies your trade log and converts it for the dashboard
- `scripts/com.mnqbot.dashboard.plist` — macOS scheduler that runs the update automatically every weekday at 23:00 Turkey time

---

## One-Time Setup (5 minutes)

### Step 1 — Copy the dashboard files into your bot folder

```bash
cp -r ~/Downloads/mnq-dashboard/index.html ~/mnq-bot/dashboard/index.html
cp -r ~/Downloads/mnq-dashboard/scripts/update_dashboard.sh ~/mnq-bot/scripts/update_dashboard.sh
cp -r ~/Downloads/mnq-dashboard/scripts/com.mnqbot.dashboard.plist ~/mnq-bot/scripts/com.mnqbot.dashboard.plist
```

### Step 2 — Make the script executable

```bash
chmod +x ~/mnq-bot/scripts/update_dashboard.sh
```

### Step 3 — Run it once manually to test

```bash
bash ~/mnq-bot/scripts/update_dashboard.sh
```

You should see: `✅ Dashboard updated — X trades`

### Step 4 — Open the dashboard

```bash
open ~/mnq-bot/dashboard/index.html
```

### Step 5 — Install the automatic scheduler

```bash
cp ~/mnq-bot/scripts/com.mnqbot.dashboard.plist \
   ~/Library/LaunchAgents/com.mnqbot.dashboard.plist

launchctl load ~/Library/LaunchAgents/com.mnqbot.dashboard.plist
```

That's it. Every weekday at 23:00 Turkey time the dashboard will update automatically.

---

## Verify the Scheduler is Running

```bash
launchctl list | grep mnqbot
```

You should see a line with `com.mnqbot.dashboard`.

---

## Manual Update Anytime

If you want to refresh the dashboard outside the schedule (e.g. during the day):

```bash
bash ~/mnq-bot/scripts/update_dashboard.sh
```

Then refresh the browser tab.

---

## Final Folder Structure

```
~/mnq-bot/
├── bot/
├── config/
├── logs/
│   ├── mnq_trades_log.csv     ← written by the bot
│   └── dashboard_update.log   ← written by the scheduler
├── dashboard/
│   ├── index.html             ← open this in browser
│   └── data/
│       ├── mnq_trades.csv     ← copy of your log
│       └── trades.js          ← auto-generated data file
└── scripts/
    ├── update_dashboard.sh
    └── com.mnqbot.dashboard.plist
```

---

## Uninstall Scheduler

```bash
launchctl unload ~/Library/LaunchAgents/com.mnqbot.dashboard.plist
rm ~/Library/LaunchAgents/com.mnqbot.dashboard.plist
```
