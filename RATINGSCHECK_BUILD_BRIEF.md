# RatingsCheck — Claude Code Build Brief

## Context

I'm building **RatingsCheck**, a daily NBA 2K player guessing game (Wordle-meets-Poeltl, but the clues are 2K attributes instead of bio facts). It's a sister project to my existing site **StatCheck** (statcheckgame.com), a 2-player sports trivia grid game I built and run.

You have a working single-file Flask prototype at `app.py` (read it first). The prototype has:
- 10 hardcoded demo players with 10 attributes each
- Session-cookie state, single-player loop, 6 guesses, 3 opening attributes that reveal one-per-wrong-guess
- Color-coded tile UI (green ≤1, yellow ≤5, orange ≤10, red >10), arrows for direction
- Two manually-curated `DAILY_PUZZLES` entries
- Endpoints: `GET /`, `GET /api/state`, `GET /api/players`, `POST /api/guess`, `POST /api/reset`

**Your job:** take this prototype to production-ready and deployable. I'll handle the actual deploy commands; you build the code and give me the deploy checklist.

## Architecture decisions (locked in — do not relitigate)

1. **Standalone Flask app on its own domain**, deployed on the **same Oracle Cloud VM** as StatCheck. New systemd service, new nginx vhost. Do not modify StatCheck's running code.
2. **Auth: single sign-on with StatCheck.** StatCheck owns the user database. RatingsCheck reads it. Practical pattern: deploy at a subdomain of statcheckgame.com (e.g. `ratings.statcheckgame.com`) so a signed cookie with `domain=.statcheckgame.com` is shared between both apps. Same Flask `secret_key` on both. StatCheck's existing login becomes RatingsCheck's login. Guests can still play without an account (localStorage-only stats).
3. **2K data: scrape with manual override.** A scheduled scraper populates the players table from 2kratings.com (top ~200 active NBA players). An admin endpoint lets me override individual attributes by hand for ratings I disagree with or that the scraper got wrong.
4. **Curation: manual with a difficulty preview.** An admin page where I pick the target player and drag/order the 10 attributes. The preview tells me "this opener narrows to N candidates among the top 200" so I can tune before committing.
5. **Database: SQLite** (`ratingscheck.db`), separate file from StatCheck's `users.db`. RatingsCheck reads StatCheck's `users.db` read-only for auth and writes everything else to its own DB.

## Before you start — ask me these

1. The absolute path to my StatCheck code on the dev machine, so you can read `app.py` to match patterns (auth, session handling, error patterns, name autocomplete via rapidfuzz, etc.).
2. The schema of StatCheck's `users` table (column names) so you don't guess.
3. The final domain — `ratings.statcheckgame.com` or something else.
4. Whether I want hard mode (tighter color tolerance ±0/±3/±7) as a v1 toggle or a v2 feature. Default to v2 if I don't answer.

Don't proceed past Phase 1 without these answers.

## Acceptance criteria

### Phase 1 — Database + real player data

- [ ] `models.py` with SQLite schema:
  - `players` (id, name, team, position, slug, speed, three, drivingDunk, midRange, layup, interiorD, perimeterD, rebounding, passAcc, strength, last_scraped, manual_overrides_json)
  - `daily_puzzles` (date PK, player_id, reveal_order_json, created_at, created_by)
  - `game_sessions` (id, user_id nullable, guest_uuid nullable, date, guesses_json, won bool, completed bool, completed_at) — one row per user per day
  - `user_stats` (user_id PK, current_streak, max_streak, total_played, total_won, distribution_json) — distribution is `{1:N, 2:N, ..., 6:N, fail:N}`
- [ ] `scraper.py` that fetches top ~200 active NBA players from 2kratings.com, parses their attribute pages, and upserts into the `players` table. Respect manual overrides on upsert (don't clobber a row's `manual_overrides_json` columns).
- [ ] `POST /admin/scrape` endpoint (auth-gated to my StatCheck username only — hardcode it in config) that runs the scraper synchronously and returns counts.
- [ ] Cron/systemd-timer instructions in a `DEPLOY.md` for weekly scraping.

### Phase 2 — SSO with StatCheck

- [ ] On startup, RatingsCheck connects read-only to StatCheck's `users.db` (path in env var `STATCHECK_USERS_DB`). Connection errors are logged but don't crash the app (login simply becomes unavailable until fixed — guests still play).
- [ ] Sessions use `app.secret_key` from env var `RATINGSCHECK_SECRET` which must match StatCheck's secret. Cookie config: `SESSION_COOKIE_DOMAIN='.statcheckgame.com'`, `SESSION_COOKIE_SECURE=True`, `SESSION_COOKIE_SAMESITE='Lax'`.
- [ ] `GET /api/me` returns `{user_id, username}` if logged in via shared cookie, else `{guest: true}`.
- [ ] If StatCheck's cookie uses a different session structure than Flask's default (read the StatCheck app.py I'll give you), match its decoding. The end result must be: I log into statcheckgame.com, hit ratings.statcheckgame.com, I'm already logged in.
- [ ] Login button on RatingsCheck redirects to `https://statcheckgame.com/login?next=https://ratings.statcheckgame.com/`. (StatCheck doesn't need code changes — its login page will land users back wherever `next` points.)

### Phase 3 — Curation admin tool

- [ ] `GET /admin/curate` (auth-gated to my StatCheck username) — page with:
  - Player search/autocomplete (rapidfuzz against the players table)
  - Drag-and-drop list of the 10 attributes to set reveal order
  - Live preview: "Opening 3 attributes narrows the field to **N players** within ±5 across all three." (N is the number of players in DB whose first 3 selected attributes are all within ±5 of the target's values.) Color this widget green if 5-20, yellow if 21-50 or 1-4, red otherwise.
  - Date picker (default = tomorrow)
  - "Save puzzle" button → writes to `daily_puzzles`
- [ ] `GET /admin/upcoming` shows the next 14 days' puzzles in a table with target name + first 3 attributes + narrowing count.
- [ ] `POST /admin/override` updates a single player's manual attribute override (player_id, attribute, value) and writes the override into `manual_overrides_json` so future scrapes don't clobber it.

### Phase 4 — Game polish & social

- [ ] On game end (win or loss), reveal **all 10 attributes** of the target side-by-side with every guess, in a "results grid" that matches the in-game tile aesthetic. This is the satisfaction payoff.
- [ ] Stats panel below results: current streak, max streak, total played, win %, guess distribution as horizontal bar chart (Wordle-style).
- [ ] **Share string** — generates and copies to clipboard:
  ```
  RatingsCheck #142 · 4/6
  🟧🟥🟩
  🟨🟧🟩🟧
  🟩🟨🟩🟨🟧
  🟩🟩🟩🟩🟩🟩
  ```
  One emoji per revealed attribute per guess. Use 🟩 / 🟨 / 🟧 / 🟥 for exact/close/warm/cold. Puzzle number = days since launch (configurable launch date in config).
- [ ] "How to play" modal on first visit (localStorage flag). Brief, with one example tile row.
- [ ] After-game state: if a user returns to the site same day after winning/losing, show the results grid + share button, not a fresh game.
- [ ] Persist `game_sessions` server-side for logged-in users; localStorage for guests.

### Phase 5 — Deploy artifacts (don't run them, just produce them)

- [ ] `ratingscheck.service` systemd unit (gunicorn, 2 workers, eventlet — match StatCheck's pattern from the app.py I'll share). Don't use the dev `app.run()` in production.
- [ ] `nginx-ratingscheck.conf` server block for `ratings.statcheckgame.com` proxying to localhost:5050 (don't reuse StatCheck's port).
- [ ] `DEPLOY.md` with the ordered commands: install deps, init DB, run scraper once, set env vars, start service, certbot for SSL, point DNS A record.
- [ ] `requirements.txt` with pinned versions.

## Style / code constraints

- **Match StatCheck patterns.** Read its `app.py` first. Same naming conventions, same error handling style, same auth helpers if portable. No bare `except: pass` (I'm trying to break that habit).
- **Werkzeug security for any password handling.** (Don't need to handle passwords directly here, just cookie/session validation.)
- **Server-side validation on every state-changing endpoint.** Client is not trusted.
- **Embedded HTML in `app.py` is fine for now** — match the prototype's pattern. If `app.py` exceeds ~1500 lines, split the HTML into `templates/index.html` and `templates/admin.html`.
- **Keep the dark Wordle aesthetic** from the prototype. Don't redesign. Add the share button, stats panel, results grid, how-to-play modal in the same visual language.
- **rapidfuzz for player name autocomplete** — match StatCheck's approach. Handle "lebron", "Lebron James", "L. James", initial-style queries.
- **No frameworks** beyond Flask + standard JS. No React, no build step. Same setup as StatCheck.

## Recurring hazards (learned the hard way on StatCheck)

- Render's ephemeral filesystem isn't a concern here (we're on Oracle Cloud) but cold-start time still matters. Don't load all player data into memory on every request — cache it once at startup.
- I have a history of accidentally dropping helper functions during manual edits and watching everything silently crash inside a try/catch. If you wrap anything in try/except, log the exception. Don't swallow.
- If you build a JS function that gets called during `loadSession()` or equivalent, make sure it's defined before it's referenced. Past bugs: function got dropped, the surrounding try/catch ate the ReferenceError, page looked fine but interaction did nothing.

## Suggested phasing

Work the phases in order. After each phase, summarize what changed, what files were touched, and what to test before I sign off. Don't move on until I confirm.

## Out of scope (don't build these — note them as v2)

- Historical 2K ratings (throwback mode). Acknowledged as cool, deferred.
- Real-time multiplayer or "compete with friends" features. Different product.
- Mobile app. Web-only for v1.
- Hard mode (tighter tolerances). Default to v2 unless I say otherwise above.

## When you're done

Don't deploy. Hand me:
1. The full code in the repo, working locally on `python app.py`
2. A `DEPLOY.md` checklist I can execute on the Oracle box
3. A list of any decisions you made that I should review (especially around the SSO cookie handshake — that's the trickiest part)
