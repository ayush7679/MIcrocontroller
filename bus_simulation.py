"""
RFID Bus Fare Management System - Software Bus Simulator
-----------------------------------------------------------------
Controls:
  SPACE -> Start / Stop the bus
  N     -> Simulate "Normal" card tap   (pays 100% fare)
  S     -> Simulate "Special" card tap  (pays 55% fare - student/senior)
  R     -> Recharge both cards (+100)
  ESC   -> Quit

Once your Arduino + RC522 is ready, replace the keyboard simulation
(see the SERIAL SECTION comments) with real serial reads from Arduino.
"""

import pygame
import time
import math
import csv
import os
import datetime

# ───────────────────────── CONFIG ─────────────────────────
WIDTH, HEIGHT = 900, 540
FPS = 60
FARE_RATE = 1        # rupees added per second while bus is moving
ROAD_Y = 330              # y-coordinate of the road surface
BUS_W, BUS_H = 110, 55
STOP_POSITIONS = [150 + (i * 230) for i in range(1000)]  # x-positions of bus stops (world space)
LOG_FILE = "transaction_log.csv"

CARD_BALANCES = {
    "NORMAL": 200.0,
    "SPECIAL": 200.0
}

# ───────────────────────── INIT ─────────────────────────
pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("RFID Bus Fare Management System")
clock = pygame.time.Clock()

font_title = pygame.font.SysFont("Segoe UI", 22, bold=True)
font_big   = pygame.font.SysFont("Segoe UI", 30, bold=True)
font_med   = pygame.font.SysFont("Segoe UI", 20, bold=True)
font_small = pygame.font.SysFont("Segoe UI", 16)

# Colors
SKY_TOP    = (90, 160, 220)
SKY_BOTTOM = (180, 220, 245)
GROUND     = (96, 168, 90)
ROAD_COL   = (60, 60, 65)
LINE_COL   = (245, 220, 90)
PANEL_BG   = (24, 28, 48)
ACCENT     = (255, 205, 60)

# ───────────────────────── STATE ─────────────────────────
world_x        = 0.0          # how far the "world" has scrolled (bus distance)
bus_moving     = False
fare           = 0.0
last_tick      = time.time()
payment_msg    = ""
payment_ok     = True
msg_timer      = 0
transactions   = []
wheel_angle    = 0
bob_offset     = 0
near_stop      = False

# ───────────────────────── HELPERS ─────────────────────────
def log_transaction(card_type, paid, balance):
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "card_type", "fare_paid", "remaining_balance"])
        writer.writerow([
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            card_type, f"{paid:.2f}", f"{balance:.2f}"
        ])


def process_payment(card_type):
    """card_type: 'NORMAL' or 'SPECIAL'"""
    global fare, payment_msg, payment_ok, msg_timer

    discount = 0.55 if card_type == "SPECIAL" else 1.0
    actual_fare = round(fare * discount, 2)
    label = "Student/Senior (55%)" if card_type == "SPECIAL" else "Normal (100%)"

    if actual_fare <= 0:
        payment_msg = "No fare accumulated yet - let the bus move!"
        payment_ok = False
    elif CARD_BALANCES[card_type] >= actual_fare:
        CARD_BALANCES[card_type] -= actual_fare
        transactions.append({"label": label, "fare": actual_fare,
                              "balance": CARD_BALANCES[card_type]})
        log_transaction(card_type, actual_fare, CARD_BALANCES[card_type])
        payment_msg = f"PAID Rs.{actual_fare:.2f} ({label}) | Balance: Rs.{CARD_BALANCES[card_type]:.2f}"
        payment_ok = True
        fare = 0.0
    else:
        payment_msg = f"LOW BALANCE on {label} card! Please recharge."
        payment_ok = False

    msg_timer = 180  # show for 3 seconds


# ───────────────────────── DRAW FUNCTIONS ─────────────────────────
def draw_background():
    # Sky gradient
    for y in range(0, ROAD_Y - 60):
        ratio = y / (ROAD_Y - 60)
        r = SKY_TOP[0] + (SKY_BOTTOM[0] - SKY_TOP[0]) * ratio
        g = SKY_TOP[1] + (SKY_BOTTOM[1] - SKY_TOP[1]) * ratio
        b = SKY_TOP[2] + (SKY_BOTTOM[2] - SKY_TOP[2]) * ratio
        pygame.draw.line(screen, (r, g, b), (0, y), (WIDTH, y))

    # Ground
    pygame.draw.rect(screen, GROUND, (0, ROAD_Y - 60, WIDTH, 60))

    # Clouds (slow parallax)
    cloud_shift = (world_x * 0.05) % (WIDTH + 200)
    for cx, cy, scale in [(120, 60, 1.0), (420, 40, 1.3), (700, 80, 0.8)]:
        x = (cx - cloud_shift) % (WIDTH + 200) - 100
        draw_cloud(x, cy, scale)

    # Distant hills
    hill_shift = (world_x * 0.15) % (WIDTH + 300)
    for hx, scale in [(100, 1.0), (450, 1.4), (800, 0.9)]:
        x = (hx - hill_shift) % (WIDTH + 300) - 150
        pygame.draw.ellipse(screen, (110, 180, 110), (x, ROAD_Y - 100, 260 * scale, 90 * scale))

    # Road
    pygame.draw.rect(screen, ROAD_COL, (0, ROAD_Y, WIDTH, HEIGHT - ROAD_Y))
    pygame.draw.rect(screen, (40, 40, 45), (0, ROAD_Y, WIDTH, 6))

    # Dashed road lines (scroll with world)
    dash_w, gap = 40, 30
    shift = int(world_x * 4) % (dash_w + gap)
    x = -shift
    while x < WIDTH:
        pygame.draw.rect(screen, LINE_COL, (x, ROAD_Y + 30, dash_w, 6), border_radius=3)
        x += dash_w + gap


def draw_cloud(x, y, scale=1.0):
    s = scale
    pygame.draw.ellipse(screen, (255, 255, 255), (x, y, 70 * s, 35 * s))
    pygame.draw.ellipse(screen, (255, 255, 255), (x + 30 * s, y - 12 * s, 55 * s, 35 * s))
    pygame.draw.ellipse(screen, (255, 255, 255), (x + 55 * s, y, 60 * s, 32 * s))


def draw_bus_stops():
    for sx in STOP_POSITIONS:
        screen_x = sx - world_x
        if -60 < screen_x < WIDTH + 60:
            pygame.draw.rect(screen, (180, 180, 190), (screen_x - 3, ROAD_Y - 90, 6, 90))
            pygame.draw.rect(screen, ACCENT, (screen_x - 28, ROAD_Y - 110, 56, 24), border_radius=4)
            lbl = font_small.render("BUS STOP", True, (40, 40, 40))
            screen.blit(lbl, (screen_x - lbl.get_width() // 2, ROAD_Y - 105))
            # shelter
            pygame.draw.line(screen, (150, 150, 160), (screen_x - 45, ROAD_Y - 5),
                              (screen_x - 45, ROAD_Y - 55), 4)
            pygame.draw.line(screen, (150, 150, 160), (screen_x - 45, ROAD_Y - 55),
                              (screen_x + 5, ROAD_Y - 55), 4)


def draw_bus(x, y):
    bob = math.sin(bob_offset) * 1.5 if bus_moving else 0
    y += bob

    # Shadow
    pygame.draw.ellipse(screen, (20, 20, 20), (x + 5, y + BUS_H - 3, BUS_W - 5, 14))

    # Body
    body_rect = (x, y, BUS_W, BUS_H)
    pygame.draw.rect(screen, (220, 60, 60), body_rect, border_radius=10)
    pygame.draw.rect(screen, (255, 255, 255), (x, y + BUS_H - 16, BUS_W, 6))  # stripe

    # Roof line
    pygame.draw.rect(screen, (180, 40, 40), (x + 4, y, BUS_W - 8, 8), border_radius=4)

    # Windows
    for i, wx in enumerate([x + 10, x + 38, x + 66]):
        pygame.draw.rect(screen, (200, 240, 255), (wx, y + 12, 22, 18), border_radius=3)
        pygame.draw.rect(screen, (255, 255, 255), (wx, y + 12, 22, 7))

    # Door
    pygame.draw.rect(screen, (60, 60, 60), (x + BUS_W - 16, y + 12, 12, 30), border_radius=2)

    # Headlight
    pygame.draw.circle(screen, (255, 255, 200), (x + BUS_W - 4, y + BUS_H - 22), 4)

    # Wheels (rotating spokes)
    for wx in [x + 22, x + BUS_W - 22]:
        wy = y + BUS_H - 2
        pygame.draw.circle(screen, (20, 20, 20), (int(wx), int(wy)), 13)
        pygame.draw.circle(screen, (180, 180, 180), (int(wx), int(wy)), 6)
        for a in range(0, 360, 90):
            ang = math.radians(a) + wheel_angle
            ex = wx + math.cos(ang) * 6
            ey = wy + math.sin(ang) * 6
            pygame.draw.line(screen, (90, 90, 90), (wx, wy), (ex, ey), 2)

    # Label
    lbl = font_small.render("CITY BUS", True, (255, 255, 255))
    screen.blit(lbl, (x + BUS_W // 2 - lbl.get_width() // 2, y + 2))

    # Exhaust puffs when moving
    if bus_moving:
        for i in range(3):
            ex = x - 6 - i * 10 - (wheel_angle * 4) % 10
            ey = y + BUS_H - 6 - i * 4
            r = 4 - i
            if r > 0:
                pygame.draw.circle(screen, (210, 210, 210), (int(ex), int(ey)), r)


def draw_panel():
    pygame.draw.rect(screen, PANEL_BG, (0, HEIGHT - 150, WIDTH, 150))
    pygame.draw.line(screen, (90, 100, 160), (0, HEIGHT - 150), (WIDTH, HEIGHT - 150), 2)

    # Fare
    fare_txt = font_big.render(f"Running Fare:  Rs. {fare:.2f}", True, ACCENT)
    screen.blit(fare_txt, (20, HEIGHT - 138))

    # Status
    status = "● BUS MOVING" if bus_moving else "■ BUS STOPPED"
    col = (90, 230, 110) if bus_moving else (240, 90, 90)
    screen.blit(font_med.render(status, True, col), (WIDTH - 200, HEIGHT - 138))

    # Card balances
    n_txt = font_med.render(f"Normal Card Balance:   Rs. {CARD_BALANCES['NORMAL']:.2f}", True, (150, 255, 170))
    s_txt = font_med.render(f"Special Card Balance:  Rs. {CARD_BALANCES['SPECIAL']:.2f}", True, (150, 200, 255))
    screen.blit(n_txt, (20, HEIGHT - 100))
    screen.blit(s_txt, (20, HEIGHT - 72))

    # Recent transactions
    screen.blit(font_small.render("Recent Transactions:", True, (180, 180, 200)), (420, HEIGHT - 100))
    for i, tx in enumerate(transactions[-3:][::-1]):
        line = f"Rs.{tx['fare']:.2f}  -  {tx['label']}  (Bal Rs.{tx['balance']:.2f})"
        screen.blit(font_small.render(line, True, (210, 210, 210)), (420, HEIGHT - 78 + i * 20))

    # Controls hint
    hint = "SPACE: Start/Stop   |   N: Tap NORMAL card   |   S: Tap SPECIAL card   |   R: Recharge cards"
    screen.blit(font_small.render(hint, True, (160, 160, 180)), (20, HEIGHT - 22))


def draw_payment_popup():
    global msg_timer
    if msg_timer > 0:
        alpha_box = pygame.Surface((WIDTH - 40, 50), pygame.SRCALPHA)
        col = (40, 160, 80, 230) if payment_ok else (180, 50, 50, 230)
        pygame.draw.rect(alpha_box, col, (0, 0, WIDTH - 40, 50), border_radius=10)
        screen.blit(alpha_box, (20, ROAD_Y - 200))

        txt = font_med.render(payment_msg, True, (255, 255, 255))
        screen.blit(txt, (20 + (WIDTH - 40 - txt.get_width()) // 2, ROAD_Y - 187))
        msg_timer -= 1


def draw_title():
    title = font_title.render("RFID Bus Fare Management System - Live Simulation", True, (255, 255, 255))
    screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 10))


# ───────────────────────── MAIN LOOP ─────────────────────────
running = True
bus_screen_x = WIDTH // 2 - BUS_W // 2   # bus stays centered; world scrolls under it

while running:
    dt = clock.tick(FPS) / 1000.0

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
            elif event.key == pygame.K_SPACE:
                bus_moving = not bus_moving
            elif event.key == pygame.K_n:
                process_payment("NORMAL")
            elif event.key == pygame.K_s:
                process_payment("SPECIAL")
            elif event.key == pygame.K_r:
                CARD_BALANCES["NORMAL"] += 100
                CARD_BALANCES["SPECIAL"] += 100

    # ── Update world ──
    if bus_moving:
        world_x += 60 * dt           # scroll speed
        wheel_angle += 6 * dt
        bob_offset += 4 * dt

        now = time.time()
        if now - last_tick >= 1.0:
            fare = round(fare + FARE_RATE, 2)
            last_tick = now
    else:
        last_tick = time.time()

    # ── Draw ──
    draw_background()
    draw_bus_stops()
    draw_bus(bus_screen_x, ROAD_Y - BUS_H)
    draw_title()
    draw_panel()
    draw_payment_popup()

    pygame.display.flip()

pygame.quit()