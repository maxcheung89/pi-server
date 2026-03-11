# Setting Up Ansible for Raspberry Pi Cluster Management

A complete guide to installing Ansible on your control machine and configuring
it to manage 5 Raspberry Pis over SSH — the exact setup used for the
OLED monitor project.

---

## What is Ansible?

Ansible is an agentless automation tool. You run commands and playbooks from
one **control machine** (your laptop or desktop), and Ansible SSHes into each
**managed node** (your Pis) to execute tasks. Nothing needs to be installed on
the Pis except Python and SSH — both already present.

```
Your Machine (control)
        │
        ├── SSH ──→ slot1_ubuntu_desktop_8gb  192.168.1.178
        ├── SSH ──→ slot2_ubuntu_server_8gb   192.168.1.179
        ├── SSH ──→ slot3_kali_pi_8gb         192.168.1.176
        ├── SSH ──→ slot4_ubuntu_server_4gb   192.168.1.175
        └── SSH ──→ slot5_ubuntu_server_2gb   192.168.1.177
```

---

## Part 1 — Install Ansible on Your Control Machine

### Linux (Ubuntu / Debian)
```bash
sudo apt update
sudo apt install ansible -y
```

### macOS
```bash
brew install ansible
```

### Any OS via pip
```bash
pip3 install ansible
```

### Verify installation
```bash
ansible --version
```

---

## Part 2 — SSH Key Setup (Passwordless Auth)

### Step 1 — Generate an SSH key on your control machine
Skip if you already have `~/.ssh/id_rsa` or `~/.ssh/id_ed25519`.
```bash
ssh-keygen -t ed25519 -C "ansible-control"
# Press Enter to accept defaults
```

### Step 2 — Copy your public key to each Pi
```bash
ssh-copy-id super90@192.168.1.175   # slot4_ubuntu_server_4gb
ssh-copy-id super90@192.168.1.176   # slot3_kali_pi_8gb
ssh-copy-id super90@192.168.1.177   # slot5_ubuntu_server_2gb
ssh-copy-id super90@192.168.1.178   # slot1_ubuntu_desktop_8gb
ssh-copy-id super90@192.168.1.179   # slot2_ubuntu_server_8gb
```

### Step 3 — Test passwordless SSH
```bash
ssh super90@192.168.1.175
# Should log in immediately with no password prompt
```

---

## Part 3 — Project Directory Structure

```bash
mkdir -p ~/ansible/{inventory,playbooks}
cd ~/ansible
```

Final layout:
```
~/ansible/
├── inventory/
│   └── hosts.ini                  ← your Pi inventory
└── playbooks/
    ├── deploy_oled.yml            ← OLED deploy + screen on/off
    ├── reboot_pis.yml             ← reboot all Pis
    ├── oled_monitor.py            ← display script
    └── oled_preview.py            ← terminal preview tool
```

---

## Part 4 — Inventory File

`inventory/hosts.ini`:
```ini
[pis]
slot4_ubuntu_server_4gb  ansible_host=192.168.1.175
slot3_kali_pi_8gb        ansible_host=192.168.1.176
slot5_ubuntu_server_2gb  ansible_host=192.168.1.177
slot1_ubuntu_desktop_8gb ansible_host=192.168.1.178
slot2_ubuntu_server_8gb  ansible_host=192.168.1.179

[pis:vars]
ansible_user=super90
ansible_become=true
ansible_become_method=sudo
ansible_python_interpreter=/usr/bin/python3
```

### What each line means

`[pis]` — group name. All Pis in this group are targeted with `hosts: pis`.

`slot4_ubuntu_server_4gb ansible_host=192.168.1.175` — alias and IP.
The alias shows in Ansible output; the IP is what it connects to.

`[pis:vars]` — variables applied to every host in `[pis]`.

| Variable | Value | Meaning |
|----------|-------|---------|
| `ansible_user` | `super90` | SSH username on each Pi |
| `ansible_become` | `true` | Use privilege escalation (sudo) |
| `ansible_become_method` | `sudo` | How to escalate |
| `ansible_python_interpreter` | `/usr/bin/python3` | Force Python 3 |

---

## Part 5 — ansible.cfg (Optional but Useful)

Create `~/ansible/ansible.cfg` to avoid typing `-i inventory/hosts.ini` every time:

```ini
[defaults]
inventory           = inventory/hosts.ini
remote_user         = super90
host_key_checking   = False
retry_files_enabled = False

[privilege_escalation]
become        = True
become_method = sudo
become_user   = root
```

With this in place from inside `~/ansible/`:
```bash
ansible-playbook playbooks/deploy_oled.yml
# instead of:
ansible-playbook -i inventory/hosts.ini playbooks/deploy_oled.yml
```

---

## Part 6 — Test Everything

### Ping all Pis
```bash
ansible -i inventory/hosts.ini pis -m ping
```

Expected output for each Pi:
```
slot4_ubuntu_server_4gb | SUCCESS => { "ping": "pong" }
slot3_kali_pi_8gb       | SUCCESS => { "ping": "pong" }
...
```

### Run a command on all Pis at once
```bash
# Uptime on all
ansible -i inventory/hosts.ini pis -m shell -a "uptime"

# OS version on all
ansible -i inventory/hosts.ini pis -m shell -a "cat /etc/os-release"

# Disk space on all
ansible -i inventory/hosts.ini pis -m shell -a "df -h /"
```

### Target a single Pi
```bash
ansible -i inventory/hosts.ini slot3_kali_pi_8gb -m ping
ansible -i inventory/hosts.ini slot1_ubuntu_desktop_8gb -m shell -a "uptime"
```

---

## Part 7 — Understanding Playbooks

A playbook is a YAML file that describes tasks to run on your hosts:

```yaml
---
- name: My first playbook
  hosts: pis
  become: true

  tasks:
    - name: Make sure curl is installed
      apt:
        name: curl
        state: present

    - name: Print hostname and IP
      debug:
        msg: "{{ inventory_hostname }} — {{ ansible_host }}"
```

Run it with:
```bash
ansible-playbook -i inventory/hosts.ini playbooks/my_first.yml
```

### Key concepts

**`hosts:`** — which group or host to run against. `pis` = all 5 Pis.

**`become: true`** — run tasks as root via sudo.

**`tasks:`** — ordered list of actions. Ansible runs top to bottom.

**Modules** — built-in actions: `apt`, `copy`, `shell`, `systemd`,
`lineinfile`, `file`, `pip`, `user`, `reboot`. Each is idempotent — safe
to run multiple times.

**`notify` / `handlers`** — a task notifies a handler (e.g. restart service)
which fires once at the end, even if notified multiple times.

---

## Part 8 — Useful Ansible Commands

### Ad-hoc commands
```bash
# Install a package on all Pis
ansible -i inventory/hosts.ini pis -m apt -a "name=htop state=present" --become

# Copy a file to all Pis
ansible -i inventory/hosts.ini pis -m copy \
  -a "src=./myfile.conf dest=/etc/myfile.conf" --become

# Restart a service on all Pis
ansible -i inventory/hosts.ini pis -m systemd \
  -a "name=oled-monitor state=restarted" --become

# Check service status on all Pis
ansible -i inventory/hosts.ini pis -m shell \
  -a "systemctl status oled-monitor --no-pager" --become

# View logs on all Pis
ansible -i inventory/hosts.ini pis -m shell \
  -a "journalctl -u oled-monitor -n 20 --no-pager" --become
```

### Playbook flags
```bash
# Dry run — show what WOULD change
ansible-playbook -i inventory/hosts.ini playbooks/deploy_oled.yml --check

# Show full diff of file changes
ansible-playbook -i inventory/hosts.ini playbooks/deploy_oled.yml --diff

# Run only tasks tagged 'deploy'
ansible-playbook -i inventory/hosts.ini playbooks/deploy_oled.yml --tags deploy

# Run against one Pi only
ansible-playbook -i inventory/hosts.ini playbooks/deploy_oled.yml \
  --limit slot1_ubuntu_desktop_8gb

# Verbose output
ansible-playbook -i inventory/hosts.ini playbooks/deploy_oled.yml -v
```

---

## Part 9 — Sudo Without a Password

Add a passwordless sudo rule on each Pi so Ansible never prompts:
```bash
ansible -i inventory/hosts.ini pis -m shell \
  -a "echo 'super90 ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/super90 && chmod 440 /etc/sudoers.d/super90" \
  --become --ask-become-pass
```
You will be prompted for the sudo password once — after this, never again.

---

## Part 10 — Troubleshooting

### "Permission denied (publickey)"
```bash
ssh-copy-id super90@192.168.1.175
```

### "sudo: a password is required"
Add `--ask-become-pass` or set up passwordless sudo (Part 9).

### "Python not found on remote"
Ensure `ansible_python_interpreter=/usr/bin/python3` is in `[pis:vars]`.

### Host unreachable
```bash
ping 192.168.1.175
ssh super90@192.168.1.175
```

---

## Quick Reference Card

```bash
# Ping all Pis
ansible -i inventory/hosts.ini pis -m ping

# Run full deploy
ansible-playbook -i inventory/hosts.ini playbooks/deploy_oled.yml

# Update script only
ansible-playbook -i inventory/hosts.ini playbooks/deploy_oled.yml --tags deploy

# Turn screens off / on
ansible-playbook -i inventory/hosts.ini playbooks/deploy_oled.yml --tags off
ansible-playbook -i inventory/hosts.ini playbooks/deploy_oled.yml --tags on

# Reboot all Pis
ansible-playbook -i inventory/hosts.ini playbooks/reboot_pis.yml

# Target one Pi
ansible-playbook -i inventory/hosts.ini playbooks/deploy_oled.yml \
  --tags deploy --limit slot3_kali_pi_8gb

# Check logs on all Pis
ansible -i inventory/hosts.ini pis -m shell \
  -a "journalctl -u oled-monitor -n 20 --no-pager" --become

# Check service status on all Pis
ansible -i inventory/hosts.ini pis -m shell \
  -a "systemctl status oled-monitor --no-pager" --become
```
