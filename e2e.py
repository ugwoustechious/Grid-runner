"""End-to-end check for Gridrunner Fight.

Drives two headless Chromium pages:
  1. local duel on one page (sanity + no console errors)
  2. the connect-code path (WebRTC, code swapped between the two pages)
  3. the server path (WebSocket relay)

Run with the static server on :8080 and the relay on :8787.
"""
import sys, time, threading, functools, http.server, socketserver, os, subprocess, socket

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = '/root/.cache/ms-playwright/chromium-1243/chrome-linux/chrome'
URL = 'http://localhost:%d/index.html'
RELAY = 'ws://localhost:8787'

from playwright.sync_api import sync_playwright

ARGS = [
    '--no-sandbox', '--disable-dev-shm-usage',
    '--disable-features=WebRtcHideLocalIpsWithMdns',
    '--autoplay-policy=no-user-gesture-required',
]

fails = []
def check(name, cond, extra=''):
    print(('  PASS  ' if cond else '  FAIL  ') + name + (('  :: ' + str(extra)) if extra and not cond else ''))
    if not cond:
        fails.append(name + ' ' + str(extra))


PORT = [0]
RELAY_PORT = [0]

def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
    handler.log_message = lambda *a, **k: None
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
    PORT[0] = httpd.server_address[1]
    httpd.serve_forever()


def new_page(browser, errors, tag):
    ctx = browser.new_context(viewport={'width': 1280, 'height': 800})
    pg = ctx.new_page()
    pg.on('console', lambda m: errors.append((tag, m.type, m.text)) if m.type == 'error' else None)
    pg.on('pageerror', lambda e: errors.append((tag, 'pageerror', str(e))))
    return pg, ctx


def wait_state(pg, pred, timeout=20):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = pg.evaluate('window.__grf ? window.__grf.state : null')
        if last and pred(last):
            return last
        pg.wait_for_timeout(120)
    return last


def screen_pos(state, idx):
    """world coordinates -> viewport pixels for a 1280x800 window"""
    sc = min(1280 / 1600.0, 800 / 1000.0)
    ox = (1280 - 1600 * sc) / 2
    oy = (800 - 1000 * sc) / 2
    return (state['x'][idx] * sc + ox, state['y'][idx] * sc + oy)


def main():
    threading.Thread(target=serve, daemon=True).start()
    time.sleep(0.6)
    global URL
    URL = URL % PORT[0]

    # pick a free port for the relay so a stale server can never be reused
    import socket as _sock
    s = _sock.socket(); s.bind(('127.0.0.1', 0)); relay_port = s.getsockname()[1]; s.close()
    relay = subprocess.Popen(['node', os.path.join(ROOT, 'server', 'server.js'), '--port', str(relay_port)],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(1.0)
    RELAY_PORT[0] = relay_port
    global RELAY
    RELAY = 'ws://localhost:%d' % relay_port
    try:
        import urllib.request
        info = urllib.request.urlopen('http://localhost:%d/health' % relay_port, timeout=5).read().decode()
        check('relay server healthy', '"ok":true' in info.replace(' ', ''), info[:120])
    except Exception as e:
        check('relay server healthy', False, e)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=EXE, args=ARGS)
        errors = []

        # ---------------------------------------------------------- local
        print('\n[1] local duel')
        pg, ctx = new_page(browser, errors, 'local')
        pg.goto(URL)
        pg.wait_for_timeout(600)
        pg.click('#splash')
        pg.wait_for_timeout(200)
        check('menu appears', not pg.is_hidden('#menu'))
        pg.click('#b_local')
        pg.wait_for_timeout(300)
        check('loadout appears', not pg.is_hidden('#loadout'))
        check('soldier cards', pg.locator('#lo_sol .card').count() == 5)
        check('weapon cards', pg.locator('#lo_wep .card').count() == 8)
        check('grenade cards', pg.locator('#lo_nade .card').count() == 6)
        pg.click('#lo_go')
        pg.wait_for_timeout(500)
        st = pg.evaluate('window.__grf.state')
        check('match running', st and st['screen'] == 'play', st)
        wait_state(pg, lambda s: s['simState'] == 'fight', 12)

        # walk towards the other fighter, then shoot them
        pg.keyboard.down('KeyD')
        pg.wait_for_timeout(2600)
        pg.keyboard.up('KeyD')
        st = pg.evaluate('window.__grf.state')
        check('player moved', st and st['x'][0] > 600, st)
        hp0 = st['hp'][1]
        for _ in range(14):
            st = pg.evaluate('window.__grf.state')
            sx, sy = screen_pos(st, 1)
            pg.mouse.move(sx, sy)
            pg.wait_for_timeout(60)
            pg.mouse.down(); pg.wait_for_timeout(90); pg.mouse.up()
            pg.wait_for_timeout(200)
            st = pg.evaluate('window.__grf.state')
            if st['hp'][1] < hp0:
                break
        check('bullets fired', st and st['ammo'][0] < 12, st)
        check('damage lands on the opponent', st and st['hp'][1] < hp0, (hp0, st['hp'][1]))
        pg.keyboard.press('Space')
        pg.wait_for_timeout(400)
        st = pg.evaluate('window.__grf.state')
        check('grenade thrown', st and st['nades'] > 0, st)
        pg.wait_for_timeout(2200)
        st = pg.evaluate('window.__grf.state')
        check('grenade detonated', st and st['nades'] == 0, st)

        # canvas is actually drawing something
        shot = pg.locator('#c').screenshot()
        check('canvas has content', len(shot) > 5000, len(shot))
        pg.close(); ctx.close()

        # ------------------------------------------------------ connect code
        print('\n[2] connect code (WebRTC)')
        pa, ca = new_page(browser, errors, 'A')
        pb, cb = new_page(browser, errors, 'B')
        pa.goto(URL); pb.goto(URL)
        pa.wait_for_timeout(500); pb.wait_for_timeout(500)
        pa.click('#splash'); pb.click('#splash')
        pa.click('#b_code'); pb.click('#b_code')
        pa.wait_for_timeout(200)

        pa.click('#cn_gen')
        pa.wait_for_function("document.getElementById('cn_code_txt').value.length > 40", timeout=25000)
        code = pa.input_value('#cn_code_txt')
        print('   host code length:', len(code))
        check('host code generated', len(code) > 40)

        pb.click('#cn_tab_guest')
        pb.fill('#cn_offer', code)
        pb.click('#cn_reply_gen')
        pb.wait_for_function("document.getElementById('cn_reply_txt').value.length > 40", timeout=25000)
        reply = pb.input_value('#cn_reply_txt')
        print('   reply code length:', len(reply))
        check('reply code generated', len(reply) > 40)

        pa.fill('#cn_answer', reply)
        pa.click('#cn_link')

        sta = wait_state(pa, lambda s: s['netState'] == 'connected', 25)
        stb = wait_state(pb, lambda s: s['netState'] == 'connected', 25)
        check('A connected', sta and sta['netState'] == 'connected', sta)
        check('B connected', stb and stb['netState'] == 'connected', stb)

        # both land on the loadout, pick, and the match starts
        pa.wait_for_timeout(700)
        check('A on loadout', pa.evaluate("window.__grf.state.screen") == 'loadout')
        check('B on loadout', pb.evaluate("window.__grf.state.screen") == 'loadout')
        # A takes the sniper so a shot can cross the arena
        pa.locator('#lo_wep .card').nth(5).click()
        pa.click('#lo_go'); pb.click('#lo_go')
        sta = wait_state(pa, lambda s: s['screen'] == 'play', 15)
        stb = wait_state(pb, lambda s: s['screen'] == 'play', 15)
        check('A playing', sta and sta['screen'] == 'play', sta)
        check('B playing', stb and stb['screen'] == 'play', stb)
        check('A is host', sta and sta['isHost'] is True, sta)
        check('B is guest', stb and stb['isHost'] is False, stb)
        check('same loadout on both sides',
              sta and stb and sta['ammo'] == stb['ammo'], (sta and sta['ammo'], stb and stb['ammo']))
        wait_state(pa, lambda s: s['simState'] == 'fight', 12)
        wait_state(pb, lambda s: s['simState'] == 'fight', 12)

        # B moves; A should see B's position change (host authority)
        x0 = sta['x'][1]
        pb.keyboard.down('KeyA')
        pb.wait_for_timeout(900)
        kb = pb.evaluate('window.__grf.state.keys')
        pb.keyboard.up('KeyA')
        sta = wait_state(pa, lambda s: abs(s['x'][1] - x0) > 2, 8) or pa.evaluate('window.__grf.state')
        check('B keyboard reaches the guest page', 'KeyA' in kb, kb)
        check('B movement replicated to A', abs(sta['x'][1] - x0) > 2, (x0, sta['x'][1]))

        # A shoots at B down the clear centre lane and B should lose health
        hp0 = pb.evaluate('window.__grf.state.hp')[1]
        for _ in range(16):
            st = pb.evaluate('window.__grf.state')
            sx, sy = screen_pos(st, 1)
            pa.mouse.move(sx, sy)
            pa.wait_for_timeout(70)
            pa.mouse.down(); pa.wait_for_timeout(70); pa.mouse.up()
            pa.wait_for_timeout(420)
            hp = pb.evaluate('window.__grf.state.hp')[1]
            if hp < hp0:
                break
        check('damage reaches the guest', hp < hp0, (hp0, hp))
        pa.close(); pb.close(); ca.close(); cb.close()

        # ------------------------------------------------------------ server
        print('\n[3] server relay')
        pa, ca = new_page(browser, errors, 'SA')
        pb, cb = new_page(browser, errors, 'SB')
        pa.goto(URL); pb.goto(URL)
        pa.wait_for_timeout(500); pb.wait_for_timeout(500)
        pa.click('#splash'); pb.click('#splash')
        pa.click('#b_server'); pb.click('#b_server')
        pa.wait_for_timeout(200)
        pa.fill('#cn_room', 'TEST42')
        pb.fill('#cn_room', 'TEST42')
        pa.fill('#cn_url', RELAY); pb.fill('#cn_url', RELAY)
        pa.click('#cn_create')
        pa.wait_for_timeout(600)
        pb.click('#cn_enter')
        sta = wait_state(pa, lambda s: s['netState'] == 'connected', 15)
        stb = wait_state(pb, lambda s: s['netState'] == 'connected', 15)
        check('A on server connected', sta and sta['netState'] == 'connected', sta)
        check('B on server connected', stb and stb['netState'] == 'connected', stb)
        pa.wait_for_timeout(600)
        pa.click('#lo_go'); pb.click('#lo_go')
        sta = wait_state(pa, lambda s: s['screen'] == 'play', 15)
        stb = wait_state(pb, lambda s: s['screen'] == 'play', 15)
        check('server match starts', sta and sta['screen'] == 'play' and stb and stb['screen'] == 'play',
              (sta, stb))
        pa.close(); pb.close(); ca.close(); cb.close()

        browser.close()

    print('\n[4] console errors')
    real = [e for e in errors if 'favicon' not in e[2].lower()]
    check('no console errors', not real, real[:6])

    relay.terminate()
    print('\n' + ('ALL CHECKS PASSED' if not fails else 'FAILURES:\n' + '\n'.join(fails)))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
