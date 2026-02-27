# OLED System Monitor — Raspberry Pi Cluster

A system monitor for 0.96" SSD1306 OLED displays (128×64px) deployed across
multiple Raspberry Pi 4B units via Ansible. All Pis show the same layout and
flip pages in sync using wall-clock time — no coordination needed.

---

## Display Layout

```
┌──────────────────────────────┐
│ IP:192.168.1.175             │  ← Line 1 — fixed, bold, scrolls if long
│ mavx_server  4GB             │  ← Line 2 — fixed, scrolls if long
│══════════════════════════════│  ← divider line (always visible)
│ CPU:23%  T:48.3C             │  ← Line 3 — flips every 5 seconds
│ Net:eth0 [UP]            ●○  │  ← Line 4 — flips every 5 seconds + page dots
└──────────────────────────────┘

Page A (first 5s)              Page B (next 5s)
  Line 3: CPU usage & temp       Line 3: Disk space & usage
  Line 4: Network + status       Line 4: Current time (live)
```

- Lines 1 and 2 are **always fixed** — they never flip
- Lines 3 and 4 **flip every 5 seconds**, synced across all Pis via wall clock
- Any line that is too wide for the screen will **scroll automatically**
- Page indicator dots `●○` / `○●` show which page you are on

---

## Hardware

### OLED Display
| Spec | Value |
|------|-------|
| Size | 0.96 inch |
| Resolution | 128 × 64 pixels |
| Driver | SSD1306 |
| Interface | I2C |
| I2C Address | `0x3C` (default) or `0x3D` |

### Wiring (same on every Pi)
```
OLED Pin   →   Raspberry Pi Header
─────────────────────────────────
VCC        →   Pin 1  (3.3V)
GND        →   Pin 6  (GND)
SCL        →   Pin 5  (GPIO 3 / I2C SCL)
SDA        →   Pin 3  (GPIO 2 / I2C SDA)
```

---

## Project Structure

```
~/ansible/
├── inventory/
│   └── hosts.ini          ← Pi inventory (IPs, user, sudo config)
├── deploy_oled.yml        ← Ansible playbook
└── oled_monitor.py        ← Python display script (deployed to each Pi)
```

---

## Inventory

`inventory/hosts.ini`:
```ini
[pis]
mavx_server    ansible_host=192.168.1.175
kali_server    ansible_host=192.168.1.176
ubuntu_server  ansible_host=192.168.1.177
ubuntu_desktop ansible_host=192.168.1.178

[pis:vars]
ansible_user=$USER  #change to your username
ansible_become=true
ansible_become_method=sudo
ansible_python_interpreter=/usr/bin/python3
```

---

## First-Time Setup

### 1. Install Ansible on your control machine
```bash
pip3 install ansible
```

### 2. Verify SSH access to all Pis
```bash
ansible -i inventory/hosts.ini pis -m ping
```
All 4 should return `pong`. If any fail, check SSH keys or passwords.

### 3. Full install (packages + I2C + service)
```bash
ansible-playbook -i inventory/hosts.ini deploy_oled.yml
```

This will:
- Install system packages (`i2c-tools`, `fonts-dejavu-core`, `python3-pip`, etc.)
- Enable I2C in `/boot/firmware/config.txt`
- Load the `i2c-dev` kernel module
- Add `super90` to the `i2c` group
- Install Python libraries (`luma.oled`, `psutil`, `Pillow`)
- Copy `oled_monitor.py` to `/opt/oled_monitor/`
- Create and start a `systemd` service that runs on boot

> **Note:** If I2C was not previously enabled on a Pi, reboot it once after the
> first deploy for the hardware change to take effect:
> ```bash
> ansible -i inventory/hosts.ini pis -m reboot --become
> ```

---

## Day-to-Day Commands

### Update the script only (no reinstall of packages)
```bash
ansible-playbook -i inventory/hosts.ini deploy_oled.yml --tags deploy
```

### Deploy to a single Pi only
```bash
ansible-playbook -i inventory/hosts.ini deploy_oled.yml --limit mavx_server
```

### Check service status on all Pis
```bash
ansible -i inventory/hosts.ini pis -m shell \
  -a "systemctl status oled-monitor --no-pager" --become
```

### View live logs from all Pis
```bash
ansible -i inventory/hosts.ini pis -m shell \
  -a "journalctl -u oled-monitor -n 20 --no-pager" --become
```

### Restart the service on all Pis
```bash
ansible -i inventory/hosts.ini pis -m shell \
  -a "systemctl restart oled-monitor" --become
```

### Stop the service on all Pis
```bash
ansible -i inventory/hosts.ini pis -m shell \
  -a "systemctl stop oled-monitor" --become
```

---

## Script Configuration

Edit these values at the top of `oled_monitor.py` before deploying:

| Variable | Default | Description |
|----------|---------|-------------|
| `I2C_ADDRESS` | `0x3C` | I2C address of your display |
| `I2C_PORT` | `1` | I2C bus number (1 for all Pi 2/3/4/5) |
| `PAGE_FLIP_SEC` | `5` | Seconds per page (synced via wall clock) |
| `FRAME_SLEEP` | `0.05` | Render loop delay (~20fps) |
| `SCROLL_SPEED` | `1` | Pixels per frame for scrolling text |
| `SCROLL_GAP` | `28` | Pixel gap between scroll loop restarts |

---

## Troubleshooting

### Display is blank after deploy
Find the actual I2C address of your display:
```bash
sudo i2cdetect -y 1
```
You will see either `3c` or `3d` in the output. Change `I2C_ADDRESS` in
`oled_monitor.py` to match (`0x3C` or `0x3D`), then redeploy:
```bash
ansible-playbook -i inventory/hosts.ini deploy_oled.yml --tags deploy
```

### "No module named luma" error in logs
```bash
ansible -i inventory/hosts.ini pis -m shell \
  -a "pip3 install luma.oled --break-system-packages" --become
```

### I2C device not found (`/dev/i2c-1` missing)
The Pi needs a reboot after I2C is first enabled:
```bash
ansible -i inventory/hosts.ini pis -m reboot --become
```

### Text lines overlapping or divider line missing
The divider line is drawn last in the render loop to prevent text from
overwriting it. If you are on an older version of the script, redeploy
the latest `oled_monitor.py`.

### One Pi is out of sync with the others on page flips
All Pis use `int(time.time() / 5) % 2` to decide which page to show.
This means they sync to UTC wall clock automatically. If one Pi is drifting,
check its system time:
```bash
timedatectl status
```
Install NTP sync if needed:
```bash
sudo apt install systemd-timesyncd -y
sudo timedatectl set-ntp true
```

---

## How Page Sync Works

No message passing or coordination between Pis is needed. Every Pi independently
calculates the current page with:

```python
page = int(time.time() / PAGE_FLIP_SEC) % 2
```

Since `time.time()` returns UTC epoch seconds, all Pis on the network will
compute the same `page` value at the same moment, as long as their clocks are
in sync (NTP handles this automatically on most Pi OS / Ubuntu installs).

---

## Files Deployed to Each Pi

| Path | Description |
|------|-------------|
| `/opt/oled_monitor/oled_monitor.py` | The display script |
| `/etc/systemd/system/oled-monitor.service` | Systemd service unit |
