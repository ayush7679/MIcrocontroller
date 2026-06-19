"""
RFID Bus Fare Management System — Kathmandu Ring Road Simulator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Controls:
  SPACE  →  Start / Stop bus
  N      →  Tap Normal card  (100% fare)
  S      →  Tap Special card (55% fare — Student/Senior)
  R      →  Recharge both cards (+Rs.100)
  ESC    →  Quit
"""

import pygame, time, math, csv, os, datetime, random

# ── CONFIG ────────────────────────────────────────────────────────
W, H        = 1100, 640
FPS         = 60
BASE_FARE   = 25.0       # Rs — minimum/starting fare
FARE_RATE   = 0.5        # Rs added per second while moving
ROAD_Y      = 340
LOG_FILE    = "transaction_log.csv"
SERIAL_PORT = "COM5"     # ← change to your port e.g. COM3, /dev/ttyUSB0

ROUTE = [
    "Kalanki","Soalte Dobato","Swayambhu","Banasthali Chowk",
    "Balaju Chowk","Gongabu","Basundhara","Chakrapath",
    "Dhumbarahi","Sukedhara","Chabahil","Mitrapark",
    "Gaushala","Airport","Tinkune","Koteshwor",
    "Balkumari","Gwarko","Satobato","Mahalaxmisthan",
    "Ekantakuna","Sanepa","Balku","Kalanki"
]

STOP_SPACING = 420
STOPS        = [i * STOP_SPACING for i in range(len(ROUTE))]
BALANCES     = {"NORMAL": 200.0, "SPECIAL": 200.0}

# ── COLOURS ───────────────────────────────────────────────────────
SKY_TOP       = ( 30,  95, 170)
SKY_BOT       = (120, 190, 235)
HILL1         = ( 55, 120,  60)
HILL2         = ( 70, 150,  75)
ROAD_C        = ( 48,  50,  56)
ROAD_SIDE     = ( 80,  82,  90)
DASH_C        = (240, 215,  55)
FOOTPATH      = (180, 165, 140)
BUILDING_COLS = [
    (180,140,100),(160,120, 90),(190,160,110),
    (140,130,120),(200,180,140),(170,145, 95),
]
PANEL_BG   = ( 12,  14,  28)
PANEL_TOP  = ( 20,  24,  45)
ACCENT     = (255, 200,  45)
GREEN_C    = ( 45, 215,  95)
RED_C      = (225,  55,  55)
GREY_C     = (175, 175, 188)
WHITE      = (255, 255, 255)
BUS_RED    = (215,  48,  48)
BUS_DARK   = (160,  28,  28)
BUS_GOLD   = (255, 210,  40)
WIN_C      = (185, 232, 255)
TYRE_C     = ( 22,  22,  28)
SIGN_GREEN = ( 20, 120,  60)
SIGN_BLUE  = ( 30,  80, 160)

# ── PYGAME INIT ───────────────────────────────────────────────────
pygame.init()
pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption("RFID Bus Fare — Kathmandu Ring Road")
clock  = pygame.time.Clock()

def fnt(sz, bold=False):
    return pygame.font.SysFont("Segoe UI", sz, bold=bold)

F = {
    "title": fnt(19, True),
    "big"  : fnt(30, True),
    "med"  : fnt(19, True),
    "sm"   : fnt(15),
    "xs"   : fnt(13),
    "xxs"  : fnt(11),
    "fare" : fnt(40, True),
    "stop" : fnt(12, True),
}

# ── SOUND ─────────────────────────────────────────────────────────
SND_OK1 = SND_OK2 = SND_FAIL = SND_TAP = SND_ARRIVE = None
HAS_SND = False
try:
    import numpy as np
    def synth(freq, dur_ms, vol=0.35):
        sr   = 44100
        n    = int(sr * dur_ms / 1000)
        t    = np.linspace(0, dur_ms/1000, n, False)
        wave = np.sin(2*np.pi*freq*t)
        fade = np.linspace(1, 0, n)**0.4
        s    = (wave * fade * vol * 32767).astype(np.int16)
        return pygame.sndarray.make_sound(np.column_stack([s, s]))
    SND_OK1    = synth(880,  120)
    SND_OK2    = synth(1100, 120)
    SND_FAIL   = synth(300,  380)
    SND_TAP    = synth(660,   70)
    SND_ARRIVE = synth(523,  200)
    HAS_SND    = True
    print("Sound: enabled")
except Exception as e:
    print(f"Sound: disabled ({e})")

def play(snd):
    if HAS_SND and snd:
        try: snd.play()
        except: pass

# ── STATE ─────────────────────────────────────────────────────────
world_x         = 0.0
moving          = False
fare            = BASE_FARE   # starts at Rs.25, ticks up Rs.0.5/sec while moving
last_tick       = time.time()
wheel_ang       = 0.0
bob             = 0.0
transactions    = []
pmsg            = ""
pmsg_ok         = True
pmsg_timer      = 0
receipt         = None
receipt_timer   = 0
total_collected = 0.0
cur_stop_idx    = 0
at_stop         = False
stop_dwell      = 0

# ── WORLD GENERATION ──────────────────────────────────────────────
random.seed(7)
buildings = []
for i, sx in enumerate(STOPS):
    bx = sx - 200
    for _ in range(random.randint(3, 6)):
        bw = random.randint(40, 80)
        bh = random.randint(45, 110)
        bc = random.choice(BUILDING_COLS)
        buildings.append({"x": bx, "w": bw, "h": bh, "col": bc,
                           "win_rows": random.randint(2,5),
                           "win_cols": random.randint(2,4)})
        bx += bw + random.randint(4, 14)

trees = []
for i in range(len(STOPS)-1):
    base = STOPS[i] + 80
    end  = STOPS[i+1] - 80
    for _ in range(random.randint(3,7)):
        tx = random.randint(int(base), max(int(base)+1, int(end)))
        trees.append({"x": tx, "h": random.randint(28,50),
                      "col": random.choice([(40,130,50),(50,145,55),(35,115,45)])})

pax_groups = []
for i, sx in enumerate(STOPS[:-1]):
    for _ in range(random.randint(2,5)):
        px = sx + random.randint(-30, 30)
        pax_groups.append({"x": px, "stop": i,
                            "col": random.choice([(80,110,200),(200,90,70),(90,160,90),(180,140,60)])})

# ── HELPERS ───────────────────────────────────────────────────────
def log_tx(card, paid, bal):
    new = not os.path.isfile(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(["timestamp","card","fare","balance"])
        w.writerow([datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    card, f"{paid:.2f}", f"{bal:.2f}"])

def send_lcd(msg):
    if arduino:
        try:
            arduino.write((msg.strip() + "\n").encode())
        except Exception as e:
            print(f"Serial error: {e}")

def get_stop_idx(wx):
    bus_pos = wx + W//2
    for i in range(len(STOPS)-1, -1, -1):
        if bus_pos >= STOPS[i]: return i
    return 0

def process(card):
    global fare, pmsg, pmsg_ok, pmsg_timer, receipt, receipt_timer, total_collected

    disc  = 0.55 if card == "SPECIAL" else 1.0
    paid  = round(fare * disc, 2)
    label = "Student/Senior" if card == "SPECIAL" else "Normal"

    if not moving and cur_stop_idx == 0 and fare <= BASE_FARE:
        pmsg       = "No fare yet — press SPACE to start the bus!"
        pmsg_ok    = False
        pmsg_timer = 180
        send_lcd("NOFFARE")
        return

    if BALANCES[card] < paid:
        pmsg       = f"LOW BALANCE — {label}  |  Only Rs.{BALANCES[card]:.2f} left"
        pmsg_ok    = False
        pmsg_timer = 220
        play(SND_FAIL)
        send_lcd("FAIL")
        return

    # ── success ──────────────────────────────────────────────────
    BALANCES[card]  = round(BALANCES[card] - paid, 2)
    total_collected = round(total_collected + paid, 2)
    transactions.append({"label": label, "fare": paid, "bal": BALANCES[card]})
    log_tx(card, paid, BALANCES[card])

    pmsg       = f"Paid Rs.{paid:.2f}  —  {label}  |  Balance: Rs.{BALANCES[card]:.2f}"
    pmsg_ok    = True
    pmsg_timer = 220

    receipt = {
        "card" : card,
        "label": label,
        "paid" : paid,
        "bal"  : BALANCES[card],
        "time" : datetime.datetime.now().strftime("%H:%M:%S"),
        "from" : ROUTE[max(0, cur_stop_idx-1)],
        "to"   : ROUTE[min(len(ROUTE)-1, cur_stop_idx)],
    }
    receipt_timer = 300
    fare          = BASE_FARE   # reset to base after payment

    play(SND_OK1)
    pygame.time.set_timer(pygame.USEREVENT+1, 180, 1)

    fare_str = f"Rs.{paid:.2f} Bal:{BALANCES[card]:.0f}"[:13].ljust(13)
    send_lcd(f"OK:{fare_str}")

# ── DRAW UTILS ────────────────────────────────────────────────────
def dr(col, x, y, w, h, r=0):
    pygame.draw.rect(screen, col, (int(x),int(y),int(w),int(h)), border_radius=r)

def dc(col, x, y, rad):
    pygame.draw.circle(screen, col, (int(x),int(y)), rad)

def dt(fkey, s, col, cx, cy, anchor="c"):
    surf = F[fkey].render(str(s), True, col)
    if   anchor=="c": screen.blit(surf,(int(cx)-surf.get_width()//2, int(cy)-surf.get_height()//2))
    elif anchor=="l": screen.blit(surf,(int(cx), int(cy)-surf.get_height()//2))
    elif anchor=="r": screen.blit(surf,(int(cx)-surf.get_width(), int(cy)-surf.get_height()//2))

# ── PRE-RENDER SKY ────────────────────────────────────────────────
sky_surf = pygame.Surface((W, ROAD_Y))
for y in range(ROAD_Y):
    r2 = y/ROAD_Y
    c  = tuple(int(SKY_TOP[i]+(SKY_BOT[i]-SKY_TOP[i])*r2) for i in range(3))
    pygame.draw.line(sky_surf, c, (0,y),(W,y))

# ── DRAW FUNCTIONS ────────────────────────────────────────────────
def draw_bg():
    screen.blit(sky_surf,(0,0))
    hs = (world_x*0.08)%(W+500)
    for hx,sc,col in [(0,1.2,HILL1),(300,1.5,HILL2),(650,1.0,HILL1),(950,1.3,HILL2)]:
        x = int((hx-hs)%(W+500))-200
        pygame.draw.ellipse(screen,col,(x,ROAD_Y-130,int(380*sc),int(100*sc)))
    for b in buildings:
        scx = int(b["x"]-world_x)
        if -120<scx<W+20:
            by = ROAD_Y-55-b["h"]
            dr(b["col"],scx,by,b["w"],b["h"])
            dr(tuple(max(0,c-30) for c in b["col"]),scx,by,b["w"],6)
            for wr in range(b["win_rows"]):
                for wc in range(b["win_cols"]):
                    wx2=scx+6+wc*14; wy2=by+10+wr*16
                    if wx2+9<scx+b["w"]-4:
                        lit=random.random()>0.35
                        dr((255,245,180) if lit else (60,70,90),wx2,wy2,9,10,1)
            dr(random.choice([SIGN_GREEN,SIGN_BLUE]),scx+4,by+b["h"]-18,b["w"]-8,14,2)
    dr(FOOTPATH,0,ROAD_Y-14,W,14)
    dr((160,145,120),0,ROAD_Y-14,W,3)
    for tr in trees:
        scx=int(tr["x"]-world_x)
        if -20<scx<W+20:
            dr((100,65,30),scx-3,ROAD_Y-14-tr["h"]//2,6,tr["h"]//2)
            dc(tr["col"],scx,ROAD_Y-14-tr["h"]//2-8,tr["h"]//3)
    dr(ROAD_C,0,ROAD_Y,W,H-ROAD_Y)
    dr(ROAD_SIDE,0,ROAD_Y,W,8)
    dr(ROAD_SIDE,0,H-20,W,20)
    dw,gap=46,28; sh=int(world_x*3.8)%(dw+gap); x=-sh
    while x<W:
        dr(DASH_C,x,ROAD_Y+38,dw,7,3); x+=dw+gap

def draw_clouds():
    cs=(world_x*0.035)%(W+400)
    for cx,cy,sc in [(60,55,1.1),(320,35,1.4),(650,65,0.9),(900,42,1.2)]:
        x=int((cx-cs)%(W+400))-160
        for dx,dy,rw,rh in [(0,0,90,38),(32,-16,68,40),(68,0,76,36)]:
            pygame.draw.ellipse(screen,(252,254,255),(x+dx,cy+dy,int(rw*sc),int(rh*sc)))

def draw_stop_scenery():
    for i,sx in enumerate(STOPS[:-1]):
        scx=int(sx-world_x)
        if -200<scx<W+200:
            name=ROUTE[i]; is_next=(i==cur_stop_idx)
            sw,sh2=110,65; sbase=ROAD_Y-16
            dr((210,200,185),scx-sw//2,sbase-sh2,sw,sh2,4)
            dr((190,180,165),scx-sw//2,sbase-sh2,sw,4)
            for px in [scx-sw//2+6,scx+sw//2-10]:
                dr((160,150,140),px,sbase-sh2,7,sh2)
            dr((30,110,55) if is_next else (60,80,50),scx-sw//2-8,sbase-sh2-6,sw+16,8,3)
            np_w=max(130,len(name)*8+16)
            dr((20,110,55),scx-np_w//2,sbase-sh2-28,np_w,22,4)
            dr((15,85,40), scx-np_w//2,sbase-sh2-28,np_w,4,4)
            dt("stop",name,WHITE,scx,sbase-sh2-17)
            dr((200,40,40),scx+np_w//2-28,sbase-sh2-28,28,22,4)
            dt("xxs","R·01",WHITE,scx+np_w//2-14,sbase-sh2-17)
            dr((140,100,70),scx-30,sbase-20,60,6,2)
            dr((120,80,50), scx-28,sbase-14,8,14,2)
            dr((120,80,50), scx+20,sbase-14,8,14,2)
            if is_next:
                pygame.draw.rect(screen,(255,220,30),
                    (scx-np_w//2-2,sbase-sh2-30,np_w+4,26),2,border_radius=5)
            for p in pax_groups:
                if p["stop"]==i:
                    px2=int(p["x"]-world_x)
                    if scx-80<px2<scx+80:
                        dc(p["col"],px2,sbase-9,5)
                        dc((235,195,165),px2,sbase-20,4)
                        pygame.draw.line(screen,p["col"],(px2,sbase-4),(px2-4,sbase+8),2)
                        pygame.draw.line(screen,p["col"],(px2,sbase-4),(px2+4,sbase+8),2)
            for zx in range(scx+sw//2+10,scx+sw//2+60,12):
                dr(WHITE,zx,ROAD_Y+2,8,20)

BW,BH=140,66

def draw_bus(bx,by):
    b=math.sin(bob)*1.8 if moving else 0
    by=int(by+b); bx=int(bx)
    pygame.draw.ellipse(screen,(10,10,12),(bx+8,by+BH+1,BW-12,10))
    dr(BUS_RED,  bx,   by,       BW,   BH,  10)
    dr(BUS_DARK, bx+4, by,       BW-8, 12,   6)
    dr(BUS_GOLD, bx,   by+BH-16, BW,    9)
    dr(BUS_DARK, bx,   by+BH-7,  BW,    7,   4)
    dr((30,30,35),   bx+BW-18,by+8, 14,32,3)
    dr((55,57,62),   bx+BW-18,by+24,14, 2)
    for wx in [bx+12,bx+46,bx+80]:
        dr(WIN_C,        wx,by+14,26,22,5)
        dr((210,242,255),wx,by+14,26, 9,5)
        pygame.draw.rect(screen,(150,180,200),(wx,by+14,26,22),1,border_radius=5)
    dr(WIN_C,        bx+BW-40,by+10,20,18,4)
    dr((210,242,255),bx+BW-40,by+10,20, 7,4)
    dc((255,252,200),bx+BW-1,by+BH-22,6)
    pygame.draw.ellipse(screen,(255,230,100),(bx+BW-3,by+BH-30,12,10))
    dc((255,120,30), bx+BW-1,by+BH-36,4)
    dc((200,30,30),  bx+3,   by+BH-22,5)
    dc((255,60,60),  bx+3,   by+BH-22,3)
    dr((20,22,38),bx+BW-62,by+2,58,14,3)
    dt("xxs","RING ROAD · RT-01",ACCENT,bx+BW-33,by+9)
    dr((20,22,38),bx+8,by+2,80,13,3)
    dt("xxs","काठमाडौं रिङ रोड",(200,220,255),bx+48,by+8)
    for wx in [bx+24,bx+BW-24]:
        wy=by+BH+2
        dc(TYRE_C,       wx,wy,15)
        dc((70,70,76),   wx,wy,10)
        dc((110,112,118),wx,wy, 5)
        for a in range(0,360,60):
            ang=math.radians(a)+wheel_ang
            ex=wx+math.cos(ang)*8; ey=wy+math.sin(ang)*8
            pygame.draw.line(screen,(95,97,104),(wx,wy),(int(ex),int(ey)),2)
    if moving:
        for i in range(4):
            ex=bx-8-i*10+math.sin(bob+i)*2; ey=by+BH-12-i*3; r=max(1,5-i)
            s2=pygame.Surface((r*2,r*2),pygame.SRCALPHA)
            pygame.draw.circle(s2,(195,195,200,170-i*38),(r,r),r)
            screen.blit(s2,(int(ex)-r,int(ey)-r))

def draw_minimap():
    mx,my,mw,mh=10,H-198,W-20,34
    dr(PANEL_TOP,mx,my,mw,mh,12)
    pygame.draw.rect(screen,(50,55,100),(mx,my,mw,mh),1,border_radius=12)
    n=len(ROUTE)-1; seg_w=(mw-24)/(n-1)
    prog=min(1.0,world_x/STOPS[-2]) if STOPS[-2]>0 else 0
    pygame.draw.line(screen,(50,54,90),(mx+12,my+mh//2),(mx+mw-12,my+mh//2),3)
    fill_x=mx+12+int((mw-24)*prog)
    pygame.draw.line(screen,ACCENT,(mx+12,my+mh//2),(fill_x,my+mh//2),3)
    for i in range(n):
        dot_x=int(mx+12+i*seg_w)
        passed=(i<cur_stop_idx) or (i==cur_stop_idx and at_stop)
        active=(i==cur_stop_idx)
        col=ACCENT if active else (GREEN_C if passed else (55,58,90))
        r=7 if active else 5
        dc(col,dot_x,my+mh//2,r)
        if active: pygame.draw.circle(screen,ACCENT,(dot_x,my+mh//2),r,2)
        if i%3==0 or active:
            nc=ACCENT if active else (130,130,160)
            ns=ROUTE[i] if len(ROUTE[i])<=10 else ROUTE[i][:9]+"."
            dt("xxs",ns,nc,dot_x,my+mh//2+(12 if i%2==0 else -13))
    dt("xxs","RING ROAD ROUTE",GREY_C,mx+mw//2,my-9)

PANEL_Y=H-158

def draw_panel():
    dr(PANEL_BG,0,PANEL_Y,W,158)
    pygame.draw.line(screen,(55,60,115),(0,PANEL_Y),(W,PANEL_Y),2)

    dr(PANEL_TOP,10,PANEL_Y+8,340,70,10)
    cur_name  = ROUTE[cur_stop_idx] if cur_stop_idx<len(ROUTE) else ROUTE[0]
    next_name = ROUTE[min(cur_stop_idx+1,len(ROUTE)-1)]
    dt("xxs","CURRENT STOP",GREY_C,       180,PANEL_Y+20)
    dt("sm",  cur_name,     ACCENT,        180,PANEL_Y+37)
    dt("xxs","NEXT STOP",  (130,180,255),  180,PANEL_Y+55)
    dt("xs",  next_name,   (160,210,255),  180,PANEL_Y+70)

    # ── RUNNING FARE — live, ticking every second ─────────────────
    dr(PANEL_TOP,360,PANEL_Y+8,220,70,10)
    dt("xxs","RUNNING FARE",GREY_C,470,PANEL_Y+22)
    dt("fare",f"Rs.{fare:.2f}",ACCENT,470,PANEL_Y+56)

    dr(PANEL_TOP,590,PANEL_Y+8,280,70,10)
    dt("xxs","NORMAL CARD",  GREY_C,          660,PANEL_Y+20)
    dt("med",f"Rs.{BALANCES['NORMAL']:.2f}",  (90,225,135), 660,PANEL_Y+48)
    dt("xxs","SPECIAL CARD", GREY_C,          800,PANEL_Y+20)
    dt("med",f"Rs.{BALANCES['SPECIAL']:.2f}", (100,175,255),800,PANEL_Y+48)

    dr(PANEL_TOP,880,PANEL_Y+8,210,70,10)
    scol=GREEN_C if moving else RED_C
    stxt="● MOVING" if moving else "■ STOPPED"
    dt("med",stxt,scol,985,PANEL_Y+28)
    dt("xxs",f"Total: Rs.{total_collected:.2f}",GREY_C,985,PANEL_Y+55)

    dr(PANEL_TOP,10,PANEL_Y+86,W-20,58,8)
    dt("xxs","RECENT TRANSACTIONS",GREY_C,110,PANEL_Y+97)
    for i,tx in enumerate(transactions[-5:][::-1]):
        col=(90,225,130) if "Normal" in tx["label"] else (100,175,255)
        s=F["xxs"].render(
            f"Rs.{tx['fare']:.2f} — {tx['label']}  (Bal Rs.{tx['bal']:.2f})",
            True,col)
        screen.blit(s,(230+i*174,PANEL_Y+91))

    hw_status=f"Arduino: {SERIAL_PORT}" if arduino else "Arduino: simulation only"
    hw_col=(55,175,75) if arduino else (200,80,80)
    dt("xxs",hw_status,hw_col,W-140,PANEL_Y+150)
    hint="SPACE: Start/Stop   N: Normal card   S: Special card   R: Recharge +Rs.100   ESC: Quit"
    dt("xxs",hint,(85,88,120),W//2-60,PANEL_Y+150)

def draw_pmsg():
    if pmsg_timer<=0: return
    col=(28,135,55) if pmsg_ok else (145,28,28)
    surf=pygame.Surface((W-20,44),pygame.SRCALPHA)
    pygame.draw.rect(surf,(*col,225),(0,0,W-20,44),border_radius=10)
    screen.blit(surf,(10,ROAD_Y-215))
    icon="✓ PAID" if pmsg_ok else "✗ FAILED"
    dt("sm",f"{icon}  |  {pmsg}",WHITE,W//2,ROAD_Y-193)

def draw_receipt():
    if not receipt or receipt_timer<=0: return
    ow,oh=400,230; ox,oy=W//2-ow//2,H//2-oh//2-50
    surf=pygame.Surface((ow,oh),pygame.SRCALPHA)
    pygame.draw.rect(surf,(18,20,42,240),(0,0,ow,oh),border_radius=16)
    pygame.draw.rect(surf,(75,80,145,200),(0,0,ow,oh),2,border_radius=16)
    screen.blit(surf,(ox,oy))
    dr((30,110,55) if receipt["card"]=="NORMAL" else (30,70,160),
       ox+ow//2-50,oy+8,100,26,13)
    dt("xxs","NORMAL CARD" if receipt["card"]=="NORMAL" else "SPECIAL CARD",
       WHITE,ox+ow//2,oy+21)
    dt("xs", "PAYMENT RECEIPT",  ACCENT,       ox+ow//2,oy+46)
    pygame.draw.line(screen,(55,60,110),(ox+16,oy+58),(ox+ow-16,oy+58),1)
    dt("xxs",receipt["label"],   GREY_C,       ox+ow//2,oy+74)
    dt("big",f"Rs. {receipt['paid']:.2f}",GREEN_C,ox+ow//2,oy+108)
    dt("xxs",f"From: {receipt['from']}  →  To: {receipt['to']}",
       GREY_C,ox+ow//2,oy+142)
    dt("xxs",f"Balance remaining: Rs. {receipt['bal']:.2f}",
       (160,200,255),ox+ow//2,oy+164)
    dt("xxs",f"Time: {receipt['time']}",GREY_C,ox+ow//2,oy+184)
    dt("xxs","[ press N / S to pay another card ]",(70,74,110),ox+ow//2,oy+210)

def draw_at_stop_banner():
    if not at_stop: return
    surf=pygame.Surface((320,38),pygame.SRCALPHA)
    pygame.draw.rect(surf,(20,100,48,220),(0,0,320,38),border_radius=10)
    screen.blit(surf,(W//2-160,ROAD_Y-260))
    name=ROUTE[cur_stop_idx] if cur_stop_idx<len(ROUTE) else ROUTE[0]
    dt("sm",f"Arrived at  {name}",WHITE,W//2,ROAD_Y-241)

def draw_title():
    dr((14,16,32),0,0,W,34)
    dt("title","RFID BUS FARE MANAGEMENT SYSTEM — KATHMANDU RING ROAD",ACCENT,W//2,17)
    hw_col=(55,175,75) if arduino else (90,94,120)
    pygame.draw.circle(screen,hw_col,(W-18,17),6)
    dt("xxs","HW" if arduino else "SIM",(165,165,185),W-30,17,"r")

# ── ARDUINO CONNECTION ────────────────────────────────────────────
arduino = None
if SERIAL_PORT:
    try:
        import serial, threading
        arduino = serial.Serial(SERIAL_PORT, 9600, timeout=1)
        time.sleep(2)

        def _listen():
            while True:
                try:
                    if arduino.in_waiting:
                        line = arduino.readline().decode(errors="ignore").strip()
                        print(f"[Arduino] {line}")
                        if   line == "NORMAL":  process("NORMAL")
                        elif line == "SPECIAL": process("SPECIAL")
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
BUS_X   = W//2 - BW//2
running = True

while running:
    dt_t = clock.tick(FPS) / 1000.0

    for e in pygame.event.get():
        if e.type == pygame.QUIT: running = False
        if e.type == pygame.KEYDOWN:
            if   e.key == pygame.K_ESCAPE: running = False
            elif e.key == pygame.K_SPACE:
                moving = not moving
                play(SND_TAP)
                if moving:
                    send_lcd("L1:Bus Running...  ")
                    time.sleep(0.05)
                    send_lcd("L2:Tap card 2 Pay  ")
                else:
                    send_lcd("L1:Bus Stopped     ")
                    time.sleep(0.05)
                    send_lcd("L2:                ")
            elif e.key == pygame.K_n: process("NORMAL")
            elif e.key == pygame.K_s: process("SPECIAL")
            elif e.key == pygame.K_r:
                BALANCES["NORMAL"]  = min(500, BALANCES["NORMAL"]  + 100)
                BALANCES["SPECIAL"] = min(500, BALANCES["SPECIAL"] + 100)
                play(SND_TAP)
                send_lcd("L1:Cards Recharged  ")
                time.sleep(0.05)
                send_lcd(f"L2:N:{BALANCES['NORMAL']:.0f} S:{BALANCES['SPECIAL']:.0f}   ")
        if e.type == pygame.USEREVENT+1: play(SND_OK2)

    # ── update world ──────────────────────────────────────────────
    new_idx = get_stop_idx(world_x)
    if new_idx != cur_stop_idx:
        cur_stop_idx = new_idx
        at_stop      = True
        stop_dwell   = 90
        moving       = False
        play(SND_ARRIVE)
        stop_name = ROUTE[cur_stop_idx][:16].ljust(16)
        send_lcd(f"L1:{stop_name}")
        time.sleep(0.05)
        send_lcd("L2:Tap card 2 Pay  ")

    if at_stop:
        stop_dwell -= 1
        if stop_dwell <= 0:
            at_stop = False

    if world_x >= STOPS[-1]:
        world_x      = 0.0
        cur_stop_idx = 0
        fare         = BASE_FARE   # reset to Rs.25, not zero

    if moving:
        world_x   += 68 * dt_t
        wheel_ang += 5  * dt_t
        bob       += 5  * dt_t
        now = time.time()
        if now - last_tick >= 1.0:
            fare      = round(fare + FARE_RATE, 2)   # +Rs.0.50 every second
            last_tick = now
    else:
        last_tick = time.time()

    if pmsg_timer    > 0: pmsg_timer    -= 1
    if receipt_timer > 0: receipt_timer -= 1

    # ── draw ──────────────────────────────────────────────────────
    draw_bg()
    draw_clouds()
    draw_stop_scenery()
    draw_bus(BUS_X, ROAD_Y-BH)
    draw_title()
    draw_minimap()
    draw_panel()
    draw_pmsg()
    draw_at_stop_banner()
    draw_receipt()
    pygame.display.flip()

pygame.quit()
if arduino: arduino.close()