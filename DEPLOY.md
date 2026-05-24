# RatingsCheck — Deploy Checklist

Target: Oracle Cloud VM, same box as StatCheck. Port 5050. Domain TBD.

---

## 1. Upload code

```bash
# From your local machine
scp -r /path/to/PythonProject6 ubuntu@<VM_IP>:/home/ubuntu/ratingscheck
```
Or clone from your repo if you have one.

---

## 2. Install Python dependencies

```bash
cd /home/ubuntu/ratingscheck
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 3. Set environment variables

Create `/home/ubuntu/ratingscheck/.env` (keep this file out of git):

```bash
# Must match StatCheck's SECRET_KEY so HMAC tokens are interoperable
RATINGSCHECK_SECRET=<same value as StatCheck SECRET_KEY>

# Your StatCheck username (lowercase). Only this user can hit /admin/* endpoints.
ADMIN_USERNAME=<your_username>

# Optional fallback password for the admin account — works even if STATCHECK_USERS_DB
# is unreachable. Use in dev or as a recovery path. Leave unset in prod if unneeded.
# ADMIN_PASSWORD=<a-strong-password>

# Phase 2 — SSO: path to StatCheck's read-only users.db for credential validation.
# Login modal on RatingsCheck validates against this DB. If unavailable, login is
# disabled but the game still works for guests.
STATCHECK_USERS_DB=/home/ubuntu/statcheck/users.db

# Phase 2 — Cookie domain. Set to .statcheckgame.com so the session cookie is
# scoped to the parent domain. Only set in production — leave unset in dev.
SESSION_COOKIE_DOMAIN=.statcheckgame.com

# Optional: path to a custom DB location
# RATINGSCHECK_DB=/home/ubuntu/ratingscheck/ratingscheck.db
```

Load it in the systemd unit (see step 5).

---

## 4. Initialize the database and run the first scrape

```bash
cd /home/ubuntu/ratingscheck
source .venv/bin/activate

# Init DB schema (safe to run multiple times)
python -c "from models import init_db; init_db(); print('DB ready')"

# First scrape — grabs all 30 NBA team rosters from 2kratings.com.
# Takes 10-20 min. If you get 403s, see the playwright fallback in scraper.py.
python scraper.py

# Verify: should print player count > 0
python -c "from models import get_all_players; print(len(get_all_players()), 'players')"
```

---

## 5. Create the systemd service

Create `/etc/systemd/system/ratingscheck.service`:

```ini
[Unit]
Description=RatingsCheck Flask App
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/ratingscheck
EnvironmentFile=/home/ubuntu/ratingscheck/.env
ExecStart=/home/ubuntu/ratingscheck/.venv/bin/gunicorn \
    --workers 2 \
    --worker-class eventlet \
    --bind 127.0.0.1:5050 \
    --timeout 120 \
    --access-logfile /var/log/ratingscheck/access.log \
    --error-logfile /var/log/ratingscheck/error.log \
    app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
# Create log dir
sudo mkdir -p /var/log/ratingscheck
sudo chown ubuntu:ubuntu /var/log/ratingscheck

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable ratingscheck
sudo systemctl start ratingscheck
sudo systemctl status ratingscheck
```

Note: `gunicorn[eventlet]` — install eventlet if not already present:
```bash
pip install eventlet
```

---

## 6. Nginx vhost

Create `/etc/nginx/sites-available/ratingscheck`:

```nginx
server {
    listen 80;
    server_name <YOUR_IP_OR_DOMAIN>;   # e.g. ratings.statcheckgame.com once DNS is set

    location / {
        proxy_pass         http://127.0.0.1:5050;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/ratingscheck /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 7. SSL (once domain DNS is pointing at the VM)

```bash
sudo certbot --nginx -d ratings.statcheckgame.com
# Follow prompts. Certbot auto-updates the nginx config and sets up auto-renewal.
```

---

## 8. Weekly scrape cron job

Add to ubuntu's crontab (`crontab -e`):

```cron
# Re-scrape 2kratings.com every Monday at 3am (ratings update weekly)
0 3 * * 1 cd /home/ubuntu/ratingscheck && /home/ubuntu/ratingscheck/.venv/bin/python scraper.py >> /var/log/ratingscheck/scrape.log 2>&1
```

Or use a systemd timer (preferred):

Create `/etc/systemd/system/ratingscheck-scrape.service`:
```ini
[Unit]
Description=RatingsCheck weekly 2K ratings scrape

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/ratingscheck
EnvironmentFile=/home/ubuntu/ratingscheck/.env
ExecStart=/home/ubuntu/ratingscheck/.venv/bin/python scraper.py
StandardOutput=append:/var/log/ratingscheck/scrape.log
StandardError=append:/var/log/ratingscheck/scrape.log
```

Create `/etc/systemd/system/ratingscheck-scrape.timer`:
```ini
[Unit]
Description=Run RatingsCheck scraper weekly

[Timer]
OnCalendar=Mon 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ratingscheck-scrape.timer
sudo systemctl list-timers ratingscheck-scrape.timer
```

---

## 9. Smoke test

```bash
# Health check (should return game state JSON)
curl http://127.0.0.1:5050/api/state

# Player list (should return array of players)
curl http://127.0.0.1:5050/api/players | python3 -m json.tool | head -20

# Admin scrape (replace TOKEN with a valid HMAC token for your admin user)
curl -X POST http://127.0.0.1:5050/admin/scrape \
     -H "Authorization: Bearer TOKEN"
```

---

## Decisions to review before going live

1. **Admin token**: `/admin/scrape` and `/admin/override` require a Bearer token signed
   with `RATINGSCHECK_SECRET`. To generate one:
   ```python
   from app import _make_token
   print(_make_token("1", "your_username"))
   ```
   The token format is identical to StatCheck's, so if both apps share the same
   `RATINGSCHECK_SECRET` = StatCheck's `SECRET_KEY`, your existing StatCheck token
   will work on RatingsCheck admin endpoints.

2. **Scraper 403s**: 2kratings.com may block requests from the VM. If so, run the
   playwright fallback (documented in `scraper.py`) or scrape locally and import the
   resulting `ratingscheck.db`.

3. **Port collision**: RatingsCheck uses 5050. Verify StatCheck is not also on 5050:
   ```bash
   sudo ss -tlnp | grep 505
   ```

4. **Domain**: When DNS is ready, update the nginx `server_name` and run certbot.
   No code changes needed.
