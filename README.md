# Gridrunner Fight

A two player duel built on **Gridrunner**. Same soldier construction, same weapon
silhouettes, same palette — but two of you in the same arena with guns and
grenades, best of three rounds.

This first build covers the **soldier, the guns and the grenades**. Companions
and techs are the next layer, and the code is laid out so they can drop in.

```
gridrunner-fight/
├── index.html          the page
├── css/style.css       all styling
├── js/
│   ├── main.js         screens, input, render loop, online session
│   ├── game.js         the versus simulation (players, bullets, grenades, rounds)
│   ├── art.js          soldier + weapon rendering, ported from Gridrunner
│   ├── data.js         soldiers, weapons, grenades, arena layout
│   ├── fx.js           particles, shockwaves, explosions
│   ├── audio.js        WebAudio sound effects (no samples)
│   └── net.js          connect code (WebRTC) and server (WebSocket) transports
├── server/
│   └── server.js       optional relay server — plain Node, no dependencies
└── test/e2e.py         end to end check of all three play paths
```

---

## Play it

### 1. On your machine

Open `index.html` through any local web server (the game uses ES modules, so
`file://` will not work):

```bash
cd gridrunner-fight
python3 -m http.server 8000
# then open http://localhost:8000
```

### 2. On GitHub

Everything is plain static files, so GitHub Pages will host it as is.

```bash
cd gridrunner-fight
git init
git add .
git commit -m "Gridrunner Fight: 2 player duel with connect codes"
git branch -M main
git remote add origin https://github.com/<your-name>/gridrunner-fight.git
git push -u origin main
```

Then in the repo: **Settings → Pages → Source: Deploy from a branch → main /
root**. Your game is live at `https://<your-name>.github.io/gridrunner-fight/`.

Set your repository link in `js/main.js` (the `REPO_URL` constant at the top) and
the "GitHub" button in the corner starts working.

---

## How to play together

### Option A — connect code (the main way)

Two devices, no server, no sign up. The connection is peer to peer over WebRTC
and the only thing that ever touches WhatsApp is a code you paste.

1. Both of you open the game and tap **Play a Friend**.
2. The host taps **Create my code** and sends the code to the friend on WhatsApp
   (there is a **Share on WhatsApp** button that opens WhatsApp with the code
   already in the message).
3. The friend taps **I was invited**, pastes the host code, and taps
   **Make my reply code**.
4. The friend sends that reply code back on WhatsApp. The host pastes it into
   **Paste your friend's reply code** and taps **Connect**.
5. Both pick a loadout and the fight starts.

The codes are about 600 characters, which is long but pastes fine in a WhatsApp
message. They are compressed SDP blobs: the game never sends them anywhere.

### Option B — server room (fallback)

If the direct connection is blocked (strict corporate wifi, some mobile
networks), both players can go through a relay instead. Run the bundled server
on any machine that can be reached:

```bash
cd gridrunner-fight/server
node server.js            # or: node server.js --port 9000
```

It prints its local and LAN addresses:

```
Gridrunner Fight relay listening on port 8787
  local   ws://localhost:8787
  network ws://192.168.1.24:8787
```

Both players choose **Server Room**, type that address, and enter the same room
code. **Quick match** drops you into any room that is waiting for a second
player.

The server is plain Node with **no dependencies** — no `npm install` needed. It
only relays messages between the two people in a room; the fight itself is
simulated by the host inside the browser.

For the internet, put the relay behind a TLS terminator or a tunnel (ngrok,
cloudflared, a VPS) and use the `wss://` address in the game.

---

## Controls

| | Player 1 | Player 2 |
|---|---|---|
| Move | `W A S D` | arrow keys |
| Aim | mouse | `I J K L` |
| Fire | left click | `Enter` |
| Grenade | `Space` | `Right Shift` |
| Reload | `R` | `Right Ctrl` |
| Swap gun | `Q` | `/` |
| Pick gun | `1` / `2` | numpad `1` / `3` |

Online, each player uses the player 1 layout on their own device. A gamepad
works as well: sticks move and aim, triggers fire.

---

## The fight

- Two rounds minimum, first to two round wins takes the match.
- 90 seconds per round. If the clock runs out, the fighter with more health wins.
- You choose a soldier, **two guns** and **one grenade** before the round.

**Soldiers** — Vanguard (balanced), Ghost (fast, fragile), Bulwark (140 HP,
slow), Medic (regenerates after 4 seconds without damage), Engineer (fast
reload).

**Guns** — Pistol, Rifle, Shotgun, SMG, Burst Rifle, Sniper, Plasma Rifle,
Revolver. Each carries its own rate of fire, spread, magazine and reload time.

**Grenades** — Frag, Cluster (five bomblets), Fire (leaves a burning zone), EMP
(stuns and clears bullets), Claymore (arms and waits), Gravity (drags you in,
then collapses). Your own ordnance never hurts you.

Bullets stop on cover blocks. The arena is mirrored around the centre so neither
fighter gets the better ground, and the centre lane is left open so the opening
shot is a fair one.

---

## How the online play works

The player who made the code is the **host**: their browser runs the whole
simulation for both fighters. The guest sends their input at 30 Hz and receives
world snapshots at the same rate, and predicts their own soldier locally so
movement stays responsive. There is no rollback and no determinism requirement,
which is why this survives a bad connection better than lockstep would.

---

## Tests

```bash
node test/codec.mjs     # connect code round trip, no browser needed
python3 test/e2e.py     # full check, needs playwright + a Chromium build
```

`e2e.py` drives two headless pages through all three paths — local duel,
connect code, server room — and checks that movement replicates to the other
side, damage lands, the relay pairs two players and the console stays clean.

---

## What comes next

The request was soldier, guns and grenades first. The places to add the rest:

- **Companions** — `js/data.js` already has the shape of the loadout data
  (`CMP` style entries with hp, range, rate). They would live as another entity
  list in `js/game.js` next to the players, following the owner.
- **Techs / turrets** — same place: a deployable entity with a life timer and a
  cooldown, like the grenades.
- **Pickups** — the arena has no loose items yet; the spawn points are hard
  coded in `Sim.resetRound`.

The original Gridrunner single player game is a separate build. This one is
only the duel.
