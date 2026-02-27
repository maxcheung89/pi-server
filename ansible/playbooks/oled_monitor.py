#!/usr/bin/env python3
"""
Raspberry Pi SSD1306 OLED Monitor (128x64 / 0.96")

Layout:
  Line 1 (fixed): IP: <ip address>
  Line 2 (fixed): <hostname>  <RAM size>
  ════════════════ divider ════════════════
  PAGE A:
    Line 3: CPU: <usage>%  <temp>C
    Line 4: Net: <iface>  [UP/DOWN]
  PAGE B:
    Line 3: Disk: <used>/<total>GB  <pct>%
    Line 4: Time: <HH:MM:SS>
"""

import time
import socket
import psutil
import threading
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
I2C_ADDRESS   = 0x3C
I2C_PORT      = 1
PAGE_FLIP_SEC = 5
FRAME_SLEEP   = 0.05       # ~20fps
DISPLAY_W     = 128
DISPLAY_H     = 64
LINE_HEIGHT   = 14
SCROLL_SPEED  = 1          # pixels per frame
SCROLL_GAP    = 28         # pixel gap between scroll loops

# Fixed Y positions
Y_LINE1   = 1
Y_LINE2   = Y_LINE1 + LINE_HEIGHT
Y_DIVIDER = Y_LINE2 + LINE_HEIGHT + 1   # pixel row for the divider
Y_LINE3   = Y_DIVIDER + 3
Y_LINE4   = Y_LINE3 + LINE_HEIGHT

try:
    font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 11
    )
    font_bold = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 11
    )
except IOError:
    font      = ImageFont.load_default()
    font_bold = font

# ──────────────────────────────────────────────
# System info
# ──────────────────────────────────────────────
def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "No IP"

def get_hostname():
    return socket.gethostname()

def get_ram_label():
    gb = psutil.virtual_memory().total / (1024 ** 3)
    if gb < 3:  return "2GB"
    if gb < 6:  return "4GB"
    return "8GB"

def get_cpu():
    pct  = psutil.cpu_percent(interval=None)
    temp = 0.0
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            temp = int(f.read()) / 1000.0
    except Exception:
        for key in ("cpu_thermal", "cpu-thermal", "coretemp"):
            t = psutil.sensors_temperatures()
            if key in t and t[key]:
                temp = t[key][0].current
                break
    return f"CPU:{pct:.0f}%  T:{temp:.1f}C"

def get_network():
    up = False
    try:
        socket.setdefaulttimeout(2)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        up = True
    except Exception:
        pass
    ifaces = []
    for iface, stat in psutil.net_if_stats().items():
        if stat.isup and iface != "lo":
            for addr in psutil.net_if_addrs().get(iface, []):
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    ifaces.append(iface.replace("ethernet", "eth")[:5])
                    break
    return f"Net:{'&'.join(ifaces) or 'None'} [{'UP' if up else 'DOWN'}]"

def get_disk():
    u = psutil.disk_usage("/")
    return f"Disk:{u.used/1024**3:.1f}/{u.total/1024**3:.0f}GB {u.percent:.0f}%"

def get_time():
    return "Time:" + datetime.now().strftime("%H:%M:%S")

# ──────────────────────────────────────────────
# Shared data store
# ──────────────────────────────────────────────
class DataStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {}
        self.refresh()

    def refresh(self):
        new = {
            "ip":      get_ip(),
            "hostname": get_hostname(),
            "ram":     get_ram_label(),
            "cpu":     get_cpu(),
            "network": get_network(),
            "disk":    get_disk(),
        }
        with self._lock:
            self._data.update(new)

    def get(self, key):
        with self._lock:
            return self._data.get(key, "")

store = DataStore()

def background_refresh():
    while True:
        time.sleep(3)
        try:
            store.refresh()
        except Exception as e:
            print(f"Refresh error: {e}")

# ──────────────────────────────────────────────
# Scroller — clips text to a safe Y band so it
# NEVER draws over the divider line
# ──────────────────────────────────────────────
def text_px_width(text, f):
    bbox = f.getbbox(text)
    return bbox[2] - bbox[0]

class Scroller:
    def __init__(self, max_height=LINE_HEIGHT):
        self.offset     = 0
        self._text      = ""
        self._font      = font
        self._width     = 0
        self._scrolling = False
        self._max_h     = max_height  # crop height — keeps text in its lane

    def set(self, text, f=None):
        if f is None:
            f = font
        if text != self._text or f != self._font:
            self._text      = text
            self._font      = f
            self._width     = text_px_width(text, f)
            self._scrolling = self._width > DISPLAY_W
            self.offset     = 0

    def reset(self):
        self.offset = 0

    def tick(self):
        if self._scrolling:
            self.offset += SCROLL_SPEED
            if self.offset >= self._width + SCROLL_GAP:
                self.offset = 0

    def draw_onto(self, image, y):
        """Draw this line onto `image` at pixel row y, strictly within max_height."""
        draw = ImageDraw.Draw(image)
        if not self._scrolling:
            # Simple static draw — clip region prevents overflow
            tmp  = Image.new("1", (DISPLAY_W, self._max_h), 0)
            tdraw = ImageDraw.Draw(tmp)
            tdraw.text((0, 0), self._text, font=self._font, fill=255)
            image.paste(tmp, (0, y))
        else:
            loop_w = self._width + SCROLL_GAP
            tmp    = Image.new("1", (loop_w * 2, self._max_h), 0)
            tdraw  = ImageDraw.Draw(tmp)
            tdraw.text((0,      0), self._text, font=self._font, fill=255)
            tdraw.text((loop_w, 0), self._text, font=self._font, fill=255)
            crop = tmp.crop((int(self.offset), 0, int(self.offset) + DISPLAY_W, self._max_h))
            image.paste(crop, (0, y))

# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    print(f"Starting OLED monitor — I2C {hex(I2C_ADDRESS)}")
    serial = i2c(port=I2C_PORT, address=I2C_ADDRESS)
    device = ssd1306(serial)
    device.contrast(200)

    s1 = Scroller(max_height=LINE_HEIGHT)   # Line 1 — IP
    s2 = Scroller(max_height=LINE_HEIGHT)   # Line 2 — hostname + RAM
    s3 = Scroller(max_height=LINE_HEIGHT)   # Line 3 — paging
    s4 = Scroller(max_height=LINE_HEIGHT)   # Line 4 — paging

    threading.Thread(target=background_refresh, daemon=True).start()

    last_page = -1

    try:
        while True:
            # ── Page sync: wall clock so all Pis flip together ──────
            page = int(time.time() / PAGE_FLIP_SEC) % 2

            # Reset bottom scrollers on page flip so they start fresh
            if page != last_page:
                s3.reset()
                s4.reset()
                last_page = page

            # ── Compose text for each line ───────────────────────────
            s1.set(f"IP:{store.get('ip')}",                font_bold)
            s2.set(f"{store.get('hostname')}  {store.get('ram')}", font)

            if page == 0:
                s3.set(store.get("cpu"),     font)
                s4.set(store.get("network"), font)
            else:
                s3.set(store.get("disk"),    font)
                s4.set(get_time(),           font)   # live every frame

            # ── Render ───────────────────────────────────────────────
            image = Image.new("1", (DISPLAY_W, DISPLAY_H), 0)

            # Draw the 4 text lines into their safe bands
            s1.draw_onto(image, Y_LINE1)
            s2.draw_onto(image, Y_LINE2)
            s3.draw_onto(image, Y_LINE3)
            s4.draw_onto(image, Y_LINE4)

            # ── Draw divider LAST so nothing overwrites it ───────────
            draw = ImageDraw.Draw(image)
            draw.line([(0, Y_DIVIDER), (DISPLAY_W, Y_DIVIDER)], fill=255)

            # Page indicator dots (bottom-right corner)
            dot_y = DISPLAY_H - 5
            draw.ellipse([DISPLAY_W-13, dot_y,   DISPLAY_W-9,  dot_y+4],
                         fill=255 if page == 0 else 0, outline=255)
            draw.ellipse([DISPLAY_W-7,  dot_y,   DISPLAY_W-3,  dot_y+4],
                         fill=255 if page == 1 else 0, outline=255)

            device.display(image)

            # Advance scrollers
            s1.tick(); s2.tick(); s3.tick(); s4.tick()

            time.sleep(FRAME_SLEEP)

    except KeyboardInterrupt:
        device.clear()
        print("Display cleared. Goodbye!")

if __name__ == "__main__":
    main()
