"""
RFID Bus Fare Management System v2 — Bus Interior View
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
View: Inside the bus, looking forward. Two overhead screens:
  LEFT screen  → Next Stop / Stop list / ETA (like a real transit display)
  RIGHT screen → Live map overview — bus position on the route
Outside the windows, the city scrolls past as the bus "moves" along
its route, matching the announced stop.

Fare logic (distance-based, tap-in / tap-out):
  Base fare           = Rs. 25  (covers first stop)
  Each stop traveled  = +Rs. 1.5
  TAP IN  → only accepted while bus is STOPPED at a stop. Starts the trip.
  TAP OUT → calculates fare from stops traveled, deducts balance.
  TAP OUT with no prior TAP IN → Rs. 200 penalty (fare evasion).

Controls:
  SPACE → Start / Stop bus
  I     → Tap IN  (Normal card)
  O     → Tap OUT (Normal card)
  J     → Tap IN  (Special card)
  K     → Tap OUT (Special card)
  R     → Recharge both cards +Rs.100
  ESC   → Quit
"""

import pygame, time, math, csv, os, datetime, random, threading

# ── CONFIG ────────────────────────────────────────────────────────
W, H         = 1200, 720
FPS          = 60
BASE_FARE    = 25.0       # Rs — covers boarding + first stop
PER_STOP     = 1.5        # Rs added per stop traveled
PENALTY_FARE = 200.0      # Rs — tap-out with no tap-in
ROAD_Y       = 430        # not used for road draw anymore, kept for compat
LOG_FILE     = "transaction_log.csv"
SERIAL_PORT  = "COM5"     # ← port selection
VOICE_ON     = True

ROUTE = [
    "Kalanki","Soalte Dobato","Swayambhu","Banasthali Chowk",
    "Balaju Chowk","Gongabu","Basundhara","Chakrapath",
    "Dhumbarahi","Sukedhara","Chabahil","Mitrapark",
    "Gaushala","Airport","Tinkune","Koteshwor",
    "Balkumari","Gwarko","Satobato","Mahalaxmisthan",
    "Ekantakuna","Sanepa","Balku","Kalanki"
]
STOP_TIME_SEC = 14         # simulated seconds between stops (for ETA display)

BALANCES = {"Balen Shah": 200.0, "Mahabir Pun": 200.0}

# ── COLOURS ───────────────────────────────────────────────────────
BUS_INTERIOR  = (58, 56, 54)
BUS_CEILING   = (44, 43, 42)
SEAT_DARK     = (40, 40, 44)
SEAT_FABRIC   = (96, 98, 108)
POLE_GOLD     = (196, 160, 40)
WIN_FRAME     = (30, 30, 32)
SKY_TOP       = ( 40, 110, 185)
SKY_BOT       = (150, 205, 240)
HILL1         = ( 55, 120,  60)
HILL2         = ( 70, 150,  75)
ROAD_C        = ( 50,  52,  58)
BUILDING_COLS = [
    (180,140,100),(160,120, 90),(190,160,110),
    (140,130,120),(200,180,140),(170,145, 95),
]
SCREEN_BG     = ( 18,  22,  34)
SCREEN_BORDER = ( 70,  78, 110)
ACCENT        = (255, 200,  45)
GREEN_C       = ( 60, 220, 110)
RED_C         = (235,  70,  70)
BLUE_C        = (100, 175, 255)
GREY_C        = (180, 184, 196)
WHITE         = (255, 255, 255)
VOICE_C       = (255, 150, 220)

# ── PYGAME INIT ───────────────────────────────────────────────────
pygame.init()
pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption("RFID Bus Fare v2 — Interior View")
clock  = pygame.time.Clock()

def fnt(sz, bold=False):
    return pygame.font.SysFont("Segoe UI", sz, bold=bold)

F = {
    "title": fnt(18, True),
    "big"  : fnt(28, True),
    "med"  : fnt(17, True),
    "sm"   : fnt(14),
    "xs"   : fnt(12),
    "xxs"  : fnt(10),
    "screen_h1": fnt(22, True),
    "screen_h2": fnt(15, True),
    "screen_b" : fnt(13),
}

# ── SOUND (sfx) ─────────────────────────────────────────────────────
SND_OK1 = SND_OK2 = SND_FAIL = SND_TAP = SND_ARRIVE = SND_PENALTY = None
HAS_SND = False
try:
    import numpy as np
    def synth(freq, dur_ms, vol=0.35):
        sr = 44100; n = int(sr*dur_ms/1000)
        t  = np.linspace(0, dur_ms/1000, n, False)
        wave = np.sin(2*np.pi*freq*t)
        fade = np.linspace(1,0,n)**0.4
        s = (wave*fade*vol*32767).astype(np.int16)
        return pygame.sndarray.make_sound(np.column_stack([s,s]))
    SND_OK1     = synth(880, 120)
    SND_OK2     = synth(1100,120)
    SND_FAIL    = synth(300, 380)
    SND_TAP     = synth(660, 70)
    SND_ARRIVE  = synth(523, 200)
    SND_PENALTY = synth(180, 500)
    HAS_SND = True
    print("Sound: enabled")
except Exception as e:
    print(f"Sound: disabled ({e})")

def play(snd):
    if HAS_SND and snd:
        try: snd.play()
        except: pass

# ── VOICE ASSISTANT ───────────────────────────────────────────────
HAS_VOICE   = False
tts_engine  = None
voice_label = ""
voice_timer = 0

if VOICE_ON:
    try:
        import pyttsx3
        tts_engine = pyttsx3.init()
        tts_engine.setProperty('rate', 165)
        tts_engine.setProperty('volume', 1.0)
        HAS_VOICE = True
        print("Voice assistant: enabled")
    except Exception as e:
        print(f"Voice assistant: disabled ({e})")

def speak(text):
    global voice_label, voice_timer
    voice_label = text
    voice_timer = 150
    if not HAS_VOICE: return
    def _say():
        try:
            tts_engine.say(text); tts_engine.runAndWait()
        except Exception as e:
            print(f"TTS error: {e}")
    threading.Thread(target=_say, daemon=True).start()

# ── STATE ─────────────────────────────────────────────────────────
world_x       = 0.0          # how far the bus has driven (px)
moving        = False
wheel_phase   = 0.0
cur_stop_idx  = 0
at_stop       = True         # bus starts parked at first stop
stop_progress = 0.0          # 0..1 between current and next stop
last_frame_t  = time.time()

transactions    = []
pmsg            = ""
pmsg_ok         = True
pmsg_timer      = 0
receipt         = None
receipt_timer   = 0
total_collected = 0.0

# tap-in tracking: card -> stop_index where they boarded (None = not on bus)
ON_BOARD = {"NORMAL": None, "SPECIAL": None}

STOP_DRIVE_SEC = 6.0   # seconds of "driving" animation between stops

# ── WORLD GENERATION (scenery seen through windows) ────────────────
random.seed(11)
buildings = []
bx = -400
while bx < 20000:
    bw = random.randint(50, 110)
    bh = random.randint(70, 170)
    bc = random.choice(BUILDING_COLS)
    buildings.append({"x": bx, "w": bw, "h": bh, "col": bc,
                       "win_rows": random.randint(3,6),
                       "win_cols": random.randint(2,4)})
    bx += bw + random.randint(20, 60)

trees = []
tx = -300
while tx < 20000:
    trees.append({"x": tx, "h": random.randint(40,70),
                  "col": random.choice([(40,130,50),(50,145,55),(35,115,45)])})
    tx += random.randint(120, 260)

# ── HELPERS ───────────────────────────────────────────────────────
def log_tx(event, card, fare, balance, from_stop, to_stop, nid=""):
    """Logs every IN, OUT, and PENALTY event for full audit trail."""
    new = not os.path.isfile(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp","event","card","fare","balance","from_stop","to_stop","nid"])
        w.writerow([
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            event, card, f"{fare:.2f}", f"{balance:.2f}", from_stop, to_stop, nid
        ])

def send_lcd(msg):
    if arduino:
        try: arduino.write((msg.strip()+"\n").encode())
        except Exception as e: print(f"Serial error: {e}")

def calc_fare(from_idx, to_idx):
    """Distance-based fare: base covers boarding, +Rs.1.5 per stop traveled."""
    stops_traveled = max(0, to_idx - from_idx)
    return round(BASE_FARE + stops_traveled * PER_STOP, 2)

def tap_in(card):
    global pmsg, pmsg_ok, pmsg_timer

    if not at_stop:
        pmsg = f"{card.title()}: Tap IN only allowed while bus is stopped!"
        pmsg_ok = False; pmsg_timer = 180
        play(SND_FAIL)
        speak("Please tap in only when the bus is stopped.")
        return

    if ON_BOARD[card] is not None:
        pmsg = f"{card.title()} card already tapped IN — tap OUT first."
        pmsg_ok = False; pmsg_timer = 180
        play(SND_FAIL)
        return

    ON_BOARD[card] = cur_stop_idx
    log_tx("IN", card, 0.0, BALANCES[card], ROUTE[cur_stop_idx], "")
    pmsg = f"{card.title()} card TAPPED IN at {ROUTE[cur_stop_idx]}"
    pmsg_ok = True; pmsg_timer = 180
    play(SND_OK1)
    send_lcd(f"L1:{card[:6]} TAP IN OK".ljust(19)[:19])
    speak(f"{'Student' if card=='SPECIAL' else 'Normal'} card tapped in.")

def tap_out(card):
    global pmsg, pmsg_ok, pmsg_timer, receipt, receipt_timer, total_collected

    boarded_at = ON_BOARD[card]

    # ── fraud case: tap-out with no tap-in ──────────────────────
    if boarded_at is None:
        if BALANCES[card] < PENALTY_FARE:
            pmsg = f"PENALTY FAILED — {card.title()} balance too low for Rs.{PENALTY_FARE:.0f} fine!"
            pmsg_ok = False; pmsg_timer = 240
            play(SND_FAIL)
            send_lcd("FAIL")
            speak("Fare evasion detected. Insufficient balance for penalty.")
            return

        BALANCES[card] = round(BALANCES[card] - PENALTY_FARE, 2)
        total_collected = round(total_collected + PENALTY_FARE, 2)
        log_tx("PENALTY", card, PENALTY_FARE, BALANCES[card], "", ROUTE[cur_stop_idx])
        pmsg = f"NO TAP-IN DETECTED — Rs.{PENALTY_FARE:.0f} PENALTY charged to {card.title()}"
        pmsg_ok = False; pmsg_timer = 280
        play(SND_PENALTY)
        send_lcd(f"OK:PENALTY Rs.200".ljust(19)[:19])
        speak(f"Fare evasion penalty. {PENALTY_FARE:.0f} rupees charged.")
        receipt = {
            "card": card, "label": "FARE EVASION PENALTY",
            "paid": PENALTY_FARE, "bal": BALANCES[card],
            "time": datetime.datetime.now().strftime("%H:%M:%S"),
            "from": "—", "to": ROUTE[cur_stop_idx], "penalty": True,
        }
        receipt_timer = 320
        return

    # ── normal tap-out ───────────────────────────────────────────
    disc  = 0.55 if card == "SPECIAL" else 1.0
    base_paid = calc_fare(boarded_at, cur_stop_idx)
    paid  = round(base_paid * disc, 2)
    label = "Student/Senior" if card == "SPECIAL" else "Normal"

    if BALANCES[card] < paid:
        pmsg = f"LOW BALANCE — {label} | Only Rs.{BALANCES[card]:.2f} left, needs Rs.{paid:.2f}"
        pmsg_ok = False; pmsg_timer = 220
        play(SND_FAIL)
        send_lcd("FAIL")
        speak("Low balance. Please recharge your card.")
        return

    BALANCES[card]  = round(BALANCES[card] - paid, 2)
    total_collected = round(total_collected + paid, 2)
    transactions.append({"label": label, "fare": paid, "bal": BALANCES[card]})
    log_tx("OUT", card, paid, BALANCES[card], ROUTE[boarded_at], ROUTE[cur_stop_idx])

    pmsg = f"{label} OUT: Rs.{paid:.2f} ({ROUTE[boarded_at]} → {ROUTE[cur_stop_idx]})"
    pmsg_ok = True; pmsg_timer = 220

    receipt = {
        "card": card, "label": label, "paid": paid, "bal": BALANCES[card],
        "time": datetime.datetime.now().strftime("%H:%M:%S"),
        "from": ROUTE[boarded_at], "to": ROUTE[cur_stop_idx], "penalty": False,
    }
    receipt_timer = 300
    ON_BOARD[card] = None   # trip complete

    play(SND_OK1)
    pygame.time.set_timer(pygame.USEREVENT+1, 180, 1)
    fare_str = f"Rs.{paid:.2f} Bal:{BALANCES[card]:.0f}"[:13].ljust(13)
    send_lcd(f"OK:{fare_str}")
    speak(f"Payment successful. {paid:.2f} rupees deducted. Balance {BALANCES[card]:.0f} rupees.")

def recharge():
    BALANCES["NORMAL"]  = min(1000, BALANCES["NORMAL"]  + 100)
    BALANCES["SPECIAL"] = min(1000, BALANCES["SPECIAL"] + 100)
    play(SND_TAP)
    send_lcd("L1:Cards Recharged ")
    speak("Both cards recharged by 100 rupees.")

# ── DRAW UTILS ────────────────────────────────────────────────────
def dr(col,x,y,w,h,r=0):
    pygame.draw.rect(screen,col,(int(x),int(y),int(w),int(h)),border_radius=r)
def dc(col,x,y,rad):
    pygame.draw.circle(screen,col,(int(x),int(y)),rad)
def dt(fkey,s,col,cx,cy,anchor="c"):
    surf = F[fkey].render(str(s),True,col)
    if   anchor=="c": screen.blit(surf,(int(cx)-surf.get_width()//2,int(cy)-surf.get_height()//2))
    elif anchor=="l": screen.blit(surf,(int(cx),int(cy)-surf.get_height()//2))
    elif anchor=="r": screen.blit(surf,(int(cx)-surf.get_width(),int(cy)-surf.get_height()//2))

# ── PRE-RENDER SKY ────────────────────────────────────────────────
SKY_H = 380
sky_surf = pygame.Surface((W, SKY_H))
for y in range(SKY_H):
    r2 = y/SKY_H
    c = tuple(int(SKY_TOP[i]+(SKY_BOT[i]-SKY_TOP[i])*r2) for i in range(3))
    pygame.draw.line(sky_surf,c,(0,y),(W,y))

# ── OUTSIDE WORLD (drawn inside window cut-outs) ───────────────────
def draw_outside_world(surf_rect):
    """Draws moving scenery clipped to the window area defined by surf_rect."""
    screen.set_clip(surf_rect)
    ox, oy, ow, oh = surf_rect
    screen.blit(pygame.transform.scale(sky_surf,(ow, int(oh*0.62))), (ox, oy))

    horizon = oy + int(oh*0.55)

    # hills
    hs = (world_x*0.10) % (ow+400)
    for hx,sc,col in [(0,1.2,HILL1),(250,1.4,HILL2),(500,1.0,HILL1)]:
        x = ox + int((hx-hs)%(ow+400)) - 150
        pygame.draw.ellipse(screen,col,(x,horizon-70,int(260*sc),int(80*sc)))

    # buildings
    for b in buildings:
        scx = ox + int(b["x"] - world_x)
        if -150 < scx-ox < ow+150:
            by = horizon - b["h"]
            dr(b["col"], scx, by, b["w"], b["h"])
            dr(tuple(max(0,c-30) for c in b["col"]), scx, by, b["w"], 5)
            for wr in range(b["win_rows"]):
                for wc in range(b["win_cols"]):
                    wx2 = scx+5+wc*12; wy2 = by+8+wr*14
                    if wx2+8 < scx+b["w"]-3:
                        lit = random.random() > 0.4
                        dr((255,245,180) if lit else (55,65,85), wx2, wy2, 7, 8, 1)

    # road
    dr(ROAD_C, ox, horizon, ow, oh - (horizon-oy), 0)
    dash_w, gap = 30, 22
    sh = int(world_x*3.0) % (dash_w+gap)
    x = ox - sh
    while x < ox+ow:
        dr((230,210,60), x, horizon+18, dash_w, 4, 2)
        x += dash_w+gap

    # trees
    for tr in trees:
        scx = ox + int(tr["x"] - world_x*1.15)
        if -30 < scx-ox < ow+30:
            dr((90,60,30), scx-2, horizon-tr["h"]//2, 4, tr["h"]//2)
            dc(tr["col"], scx, horizon-tr["h"]//2-6, tr["h"]//3)

    screen.set_clip(None)

# ── BUS INTERIOR ──────────────────────────────────────────────────
def draw_interior():
    # ceiling
    dr(BUS_CEILING, 0, 0, W, 70)
    # side walls (above window line)
    dr(BUS_INTERIOR, 0, 0, W, H)

    # windshield big window (top center, where the road is visible ahead)
    windshield = (W//2-330, 70, 660, 230)
    dr(WIN_FRAME, windshield[0]-10, windshield[1]-10, windshield[2]+20, windshield[3]+20, 14)
    draw_outside_world(windshield)
    pygame.draw.rect(screen, WIN_FRAME, windshield, 6, border_radius=8)

    # side windows (left & right strips, partial scenery for depth)
    for side_x in [40, W-40-220]:
        sw = (side_x, 110, 220, 150)
        dr(WIN_FRAME, sw[0]-8, sw[1]-8, sw[2]+16, sw[3]+16, 12)
        draw_outside_world(sw)
        pygame.draw.rect(screen, WIN_FRAME, sw, 5, border_radius=6)

    # grab poles (yellow)
    for px in [170, 430, W-430, W-170]:
        dr(POLE_GOLD, px-6, 60, 12, 260, 4)
        dc(POLE_GOLD, px, 60, 9)

    # seat backs (foreground, bottom of screen, looking forward over them)
    seat_y = H - 150
    for i, sx in enumerate([40, 230, W-230-180, W-180]):
        dr(SEAT_DARK, sx, seat_y, 180, 150, 14)
        dr(SEAT_FABRIC, sx+10, seat_y+14, 160, 60, 8)
        dr(SEAT_DARK, sx+8, seat_y-22, 164, 30, 10)  # headrest

# ── SCREEN 1 — NEXT STOP DISPLAY (left monitor) ────────────────────
def draw_stop_screen():
    sx, sy, sw, sh = 70, 320, 430, 150
    dr((10,12,18), sx-6, sy-6, sw+12, sh+12, 12)
    dr(SCREEN_BG, sx, sy, sw, sh, 8)
    pygame.draw.rect(screen, SCREEN_BORDER, (sx,sy,sw,sh), 2, border_radius=8)

    cur_name  = ROUTE[cur_stop_idx]
    next_name = ROUTE[min(cur_stop_idx+1, len(ROUTE)-1)]

    dt("xs", "NEXT STOP:", GREY_C, sx+14, sy+18, "l")
    dt("screen_h1", next_name.upper() if moving else f"AT {cur_name.upper()}",
       ACCENT, sx+14, sy+42, "l")

    # mini upcoming-stops list with ETA
    list_y = sy+72
    for k in range(3):
        idx = min(cur_stop_idx+1+k, len(ROUTE)-1)
        if idx == cur_stop_idx: continue
        eta_sec = int(STOP_TIME_SEC*(k+ (stop_progress if k==0 else 1) if moving else (k+1)))
        eta_sec = max(1, STOP_TIME_SEC*(k+1) - int(stop_progress*STOP_TIME_SEC))
        mm = eta_sec//60; ss = eta_sec%60
        dt("screen_b", f"• {ROUTE[idx]}", GREY_C, sx+18, list_y+k*20, "l")
        dt("screen_b", f"{mm}:{ss:02d}", (150,200,255), sx+sw-50, list_y+k*20, "l")

    # status bar
    dr((10,12,18), sx, sy+sh-26, sw, 26, 0)
    now = datetime.datetime.now().strftime("%I:%M %p")
    dt("xxs", f"TIME: {now}  |  Rs.{BASE_FARE:.0f} base + Rs.{PER_STOP:.1f}/stop",
       (150,155,175), sx+10, sy+sh-13, "l")

# ── SCREEN 2 — LIVE MAP OVERVIEW (right monitor) ───────────────────
def draw_map_screen():
    sx, sy, sw, sh = W-500, 320, 430, 150
    dr((10,12,18), sx-6, sy-6, sw+12, sh+12, 12)
    dr(SCREEN_BG, sx, sy, sw, sh, 8)
    pygame.draw.rect(screen, SCREEN_BORDER, (sx,sy,sw,sh), 2, border_radius=8)

    dt("xs", "MAP OVERVIEW — RING ROAD", GREY_C, sx+14, sy+16, "l")

    # route line
    n = len(ROUTE)-1
    map_x0, map_x1 = sx+18, sx+sw-18
    map_y = sy+70
    pygame.draw.line(screen, (60,64,100), (map_x0,map_y), (map_x1,map_y), 4)

    seg_w = (map_x1-map_x0)/n
    progress_frac = (cur_stop_idx + (stop_progress if moving else 0)) / n
    fill_x = map_x0 + (map_x1-map_x0)*progress_frac
    pygame.draw.line(screen, ACCENT, (map_x0,map_y), (fill_x,map_y), 4)

    for i in range(n+1):
        dx = map_x0 + i*seg_w
        passed = i < cur_stop_idx or (i==cur_stop_idx)
        col = ACCENT if i==cur_stop_idx else (GREEN_C if i<cur_stop_idx else (70,74,110))
        dc(col, dx, map_y, 5 if i!=cur_stop_idx else 7)

    # "YOU ARE HERE" marker
    bus_dx = map_x0 + (map_x1-map_x0)*progress_frac
    dc((255,90,90), bus_dx, map_y-16, 6)
    dt("xxs", "YOU ARE HERE", (255,140,140), bus_dx, map_y-30, "c")

    # stop name labels for current/next only (avoid clutter)
    dt("screen_b", ROUTE[cur_stop_idx], WHITE, map_x0, map_y+22, "l")
    dt("xxs", "current", GREY_C, map_x0, map_y+38, "l")
    nn = ROUTE[min(cur_stop_idx+1,n)]
    dt("screen_b", nn, (160,210,255), map_x1, map_y+22, "r")
    dt("xxs", "next", GREY_C, map_x1, map_y+38, "r")

    # footer info bar
    dr((10,12,18), sx, sy+sh-26, sw, 26, 0)
    dt("xxs", f"Route RT-01 · {len(ROUTE)} stops · Live GPS sim", (150,155,175), sx+10, sy+sh-13, "l")

# ── TOP STATUS BAR ─────────────────────────────────────────────────
def draw_topbar():
    dr((12,14,20), 0, 0, W, 26)
    dt("xs", "RFID BUS FARE SYSTEM v2 — TAP IN / TAP OUT", ACCENT, W//2, 13)
    hw_col = (60,200,90) if arduino else (90,94,120)
    dc(hw_col, 16, 13, 5)
    dt("xxs", "HW" if arduino else "SIM", (170,174,190), 28, 13, "l")
    vc_col = VOICE_C if HAS_VOICE else (90,94,120)
    dc(vc_col, W-90, 13, 5)
    dt("xxs", "VOICE", vc_col, W-80, 13, "l")
    scol = GREEN_C if moving else RED_C
    dt("xxs", "● MOVING" if moving else "■ STOPPED", scol, W-180, 13, "l")

# ── BOTTOM HUD PANEL ────────────────────────────────────────────────
PANEL_Y = H - 150

def draw_hud():
    dr((10,12,20), 0, PANEL_Y, W, 150)
    pygame.draw.line(screen,(50,54,90),(0,PANEL_Y),(W,PANEL_Y),2)

    # card balances + onboard status
    dr((20,24,40), 14, PANEL_Y+10, 330, 80, 10)
    dt("xxs","NORMAL CARD",GREY_C, 30, PANEL_Y+24, "l")
    dt("med", f"Rs.{BALANCES['NORMAL']:.2f}", GREEN_C, 30, PANEL_Y+46, "l")
    onb = "ON BUS (boarded: " + ROUTE[ON_BOARD["NORMAL"]] + ")" if ON_BOARD["NORMAL"] is not None else "not boarded"
    dt("xxs", onb, (150,200,150) if ON_BOARD["NORMAL"] is not None else (130,130,150), 30, PANEL_Y+66, "l")

    dt("xxs","SPECIAL CARD",GREY_C, 220, PANEL_Y+24, "l")
    dt("med", f"Rs.{BALANCES['SPECIAL']:.2f}", BLUE_C, 220, PANEL_Y+46, "l")
    onb2 = "ON BUS (boarded: " + ROUTE[ON_BOARD["SPECIAL"]] + ")" if ON_BOARD["SPECIAL"] is not None else "not boarded"
    dt("xxs", onb2, (150,180,220) if ON_BOARD["SPECIAL"] is not None else (130,130,150), 220, PANEL_Y+66, "l")

    # revenue
    dr((20,24,40), 360, PANEL_Y+10, 220, 80, 10)
    dt("xxs","TOTAL REVENUE", GREY_C, 470, PANEL_Y+26, "c")
    dt("big", f"Rs.{total_collected:.2f}", ACCENT, 470, PANEL_Y+58, "c")

    # recent transactions
    dr((20,24,40), 596, PANEL_Y+10, W-610, 80, 10)
    dt("xxs","RECENT TRANSACTIONS", GREY_C, 700, PANEL_Y+22, "l")
    for i, tx in enumerate(transactions[-4:][::-1]):
        col = GREEN_C if "Normal" in tx["label"] else BLUE_C
        dt("xxs", f"Rs.{tx['fare']:.2f} — {tx['label']}", col, 606+i*210, PANEL_Y+46, "l")

    hint = "I: Tap-IN Normal   O: Tap-OUT Normal   J: Tap-IN Special   K: Tap-OUT Special   SPACE: Drive   R: Recharge   ESC: Quit"
    dt("xxs", hint, (110,114,140), W//2, PANEL_Y+145)

def draw_pmsg():
    if pmsg_timer<=0: return
    col = (28,135,55) if pmsg_ok else (145,28,28)
    surf = pygame.Surface((W-40,40), pygame.SRCALPHA)
    pygame.draw.rect(surf,(*col,230),(0,0,W-40,40),border_radius=10)
    screen.blit(surf,(20,300))
    icon = "✓" if pmsg_ok else "✗"
    dt("sm", f"{icon}  {pmsg}", WHITE, W//2, 320)

def draw_voice_caption():
    if voice_timer<=0 or not voice_label: return
    ow = min(W-60, 26+len(voice_label)*8)
    ox = W//2-ow//2
    surf = pygame.Surface((ow,32), pygame.SRCALPHA)
    pygame.draw.rect(surf,(60,20,55,225),(0,0,ow,32),border_radius=16)
    screen.blit(surf,(ox, 480))
    dt("xs", f"🔊 {voice_label}", VOICE_C, W//2, 496)

def draw_receipt():
    if not receipt or receipt_timer<=0: return
    ow,oh = 420,230
    ox,oy = W//2-ow//2, H//2-oh//2-40
    surf = pygame.Surface((ow,oh), pygame.SRCALPHA)
    pen = receipt.get("penalty", False)
    bgcol = (90,20,20,240) if pen else (18,20,42,240)
    pygame.draw.rect(surf,bgcol,(0,0,ow,oh),border_radius=16)
    pygame.draw.rect(surf,(150,40,40,220) if pen else (75,80,145,200),(0,0,ow,oh),2,border_radius=16)
    screen.blit(surf,(ox,oy))
    badge_col = (140,20,20) if pen else ((30,110,55) if receipt["card"]=="NORMAL" else (30,70,160))
    dr(badge_col, ox+ow//2-60, oy+8, 120, 26, 13)
    dt("xxs", "PENALTY" if pen else ("NORMAL CARD" if receipt["card"]=="NORMAL" else "SPECIAL CARD"),
       WHITE, ox+ow//2, oy+21)
    dt("xs","FARE EVASION NOTICE" if pen else "PAYMENT RECEIPT", (255,150,150) if pen else ACCENT, ox+ow//2, oy+46)
    pygame.draw.line(screen,(90,40,40) if pen else (55,60,110),(ox+16,oy+58),(ox+ow-16,oy+58),1)
    dt("xxs", receipt["label"], GREY_C, ox+ow//2, oy+74)
    dt("big", f"Rs. {receipt['paid']:.2f}", (255,110,110) if pen else GREEN_C, ox+ow//2, oy+110)
    dt("xxs", f"From: {receipt['from']}  →  To: {receipt['to']}", GREY_C, ox+ow//2, oy+146)
    dt("xxs", f"Balance remaining: Rs. {receipt['bal']:.2f}", (160,200,255), ox+ow//2, oy+168)
    dt("xxs", f"Time: {receipt['time']}", GREY_C, ox+ow//2, oy+188)
    dt("xxs", "[ tap card to continue ]", (70,74,110), ox+ow//2, oy+210)

def draw_at_stop_banner():
    if not at_stop: return
    surf = pygame.Surface((360,36), pygame.SRCALPHA)
    pygame.draw.rect(surf,(20,100,48,220),(0,0,360,36),border_radius=10)
    screen.blit(surf,(W//2-180, 96))
    dt("sm", f"Stopped at  {ROUTE[cur_stop_idx]}", WHITE, W//2, 114)

# ── ARDUINO CONNECTION (dual reader support) ────────────────────────
arduino = None
if SERIAL_PORT:
    try:
        import serial
        arduino = serial.Serial(SERIAL_PORT, 9600, timeout=1)
        time.sleep(2)

        def _listen():
            while True:
                try:
                    if arduino.in_waiting:
                        line = arduino.readline().decode(errors="ignore").strip()
                        print(f"[Arduino] {line}")
                        # Expected protocol from dual-reader sketch:
                        #   IN:NORMAL  IN:SPECIAL  OUT:NORMAL  OUT:SPECIAL
                        if line.startswith("IN:"):
                            card = line.split(":")[1]
                            if card in ("NORMAL","SPECIAL"): tap_in(card)
                        elif line.startswith("OUT:"):
                            card = line.split(":")[1]
                            if card in ("NORMAL","SPECIAL"): tap_out(card)
                        elif line.startswith("UNKNOWN"):
                            print(f"  Unregistered UID: {line}")
                        elif line == "READY":
                            print("  Arduino ready")
                except Exception as e:
                    print(f"Serial read error: {e}")
                time.sleep(0.05)

        threading.Thread(target=_listen, daemon=True).start()
        print(f"Arduino connected on {SERIAL_PORT}")
    except Exception as e:
        arduino = None
        print(f"Arduino not found ({e}) — keyboard simulation mode")

# ── MAIN LOOP ─────────────────────────────────────────────────────
running = True
while running:
    dt_t = clock.tick(FPS)/1000.0

    for e in pygame.event.get():
        if e.type == pygame.QUIT: running = False
        if e.type == pygame.KEYDOWN:
            if   e.key == pygame.K_ESCAPE: running = False
            elif e.key == pygame.K_SPACE:
                if at_stop:
                    moving = True
                    at_stop = False
                    play(SND_TAP)
                    speak("Bus departing.")
            elif e.key == pygame.K_i: tap_in("NORMAL")
            elif e.key == pygame.K_o: tap_out("NORMAL")
            elif e.key == pygame.K_j: tap_in("SPECIAL")
            elif e.key == pygame.K_k: tap_out("SPECIAL")
            elif e.key == pygame.K_r: recharge()
        if e.type == pygame.USEREVENT+1: play(SND_OK2)

    # ── world / stop progression ────────────────────────────────
    if moving:
        world_x += 90*dt_t
        wheel_phase += 4*dt_t
        stop_progress += dt_t/STOP_DRIVE_SEC
        if stop_progress >= 1.0:
            stop_progress = 0.0
            moving = False
            at_stop = True
            cur_stop_idx = (cur_stop_idx+1) % len(ROUTE)
            if cur_stop_idx == 0:
                world_x = 0.0
            play(SND_ARRIVE)
            send_lcd(f"L1:{ROUTE[cur_stop_idx][:16].ljust(16)}")
            time.sleep(0.02)
            send_lcd("L2:Tap card to pay ")
            speak(f"Stop. {ROUTE[cur_stop_idx]}.")

    if pmsg_timer>0: pmsg_timer-=1
    if receipt_timer>0: receipt_timer-=1
    if voice_timer>0: voice_timer-=1

    # ── draw ─────────────────────────────────────────────────────
    screen.fill((0,0,0))
    draw_interior()
    draw_topbar()
    draw_stop_screen()
    draw_map_screen()
    draw_pmsg()
    draw_voice_caption()
    draw_at_stop_banner()
    draw_receipt()
    draw_hud()
    pygame.display.flip()

pygame.quit()
if arduino: arduino.close()
