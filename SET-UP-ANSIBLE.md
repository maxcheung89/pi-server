# Setting Up Ansible for Raspberry Pi Cluster Management

A complete guide to installing Ansible on your control machine and configuring
it to manage multiple Raspberry Pis over SSH — the exact setup used for the
OLED monitor project.

---

## What is Ansible?

Ansible is an agentless automation tool. You run commands and playbooks from
one **control machine** (your laptop or desktop), and Ansible SSHes into each
**managed node** (your Pis) to execute tasks. Nothing needs to be installed on
the Pis except Python and SSH — both of which are already there.

```
Your Machine (control)
        │
        ├── SSH ──→ mavx_server    192.168.1.175
        ├── SSH ──→ kali_server    192.168.1.176
        ├── SSH ──→ ubuntu_server  192.168.1.177
        └── SSH ──→ ubuntu_desktop 192.168.1.178
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
You should see output like `ansible [core 2.x.x]`.

---

## Part 2 — SSH Key Setup (Passwordless Auth)

Ansible works best with SSH key authentication so it never has to prompt for
a password during a playbook run.

### Step 1 — Generate an SSH key on your control machine
Skip this if you already have `~/.ssh/id_rsa` or `~/.ssh/id_ed25519`.
```bash
ssh-keygen -t ed25519 -C "ansible-control"
# Press Enter to accept defaults (no passphrase needed for automation)
```

### Step 2 — Copy your public key to each Pi
Run this once per Pi, replacing the IP each time:
```bash
ssh-copy-id super90@192.168.1.175
ssh-copy-id super90@192.168.1.176
ssh-copy-id super90@192.168.1.177
ssh-copy-id super90@192.168.1.178
```
You will be prompted for the password of `super90` once per Pi. After this,
SSH will log in without a password.

### Step 3 — Test passwordless SSH manually
```bash
ssh super90@192.168.1.175
# Should log in immediately with no password prompt
```

---

## Part 3 — Project Directory Structure

Create a clean Ansible workspace:
```bash
mkdir -p ~/ansible/inventory
cd ~/ansible
```

Your final layout will look like this:
```
~/ansible/
├── ansible.cfg            ← Ansible settings (optional but recommended)
├── inventory/
│   └── hosts.ini          ← List of your Pis
└── playbooks/
    └── deploy_oled.yml    ← Your playbooks go here
    └── oled_monitor.py    ← Files to deploy go alongside playbooks
```

---

## Part 4 — Inventory File

The inventory tells Ansible which machines exist and how to reach them.

Create `~/ansible/inventory/hosts.ini`:
```ini
[pis]
mavx_server    ansible_host=192.168.1.175
kali_server    ansible_host=192.168.1.176
ubuntu_server  ansible_host=192.168.1.177
ubuntu_desktop ansible_host=192.168.1.178

[pis:vars]
ansible_user=super90
ansible_become=true
ansible_become_method=sudo
ansible_python_interpreter=/usr/bin/python3
```

### What each line means

`[pis]` — group name. You can have multiple groups like `[webservers]`, `[databases]`.
Every Pi in this group can be targeted with `hosts: pis` in a playbook.

`mavx_server ansible_host=192.168.1.175` — a host alias and its IP.
The alias is what shows up in Ansible output; the IP is what it connects to.

`[pis:vars]` — variables that apply to every host in `[pis]`.

| Variable | Value | Meaning |
|----------|-------|---------|
| `ansible_user` | `super90` | SSH username on the Pi |
| `ansible_become` | `true` | Use privilege escalation (sudo) |
| `ansible_become_method` | `sudo` | How to escalate (sudo is default) |
| `ansible_python_interpreter` | `/usr/bin/python3` | Force Python 3 on managed nodes |

---

## Part 5 — ansible.cfg (Optional but Useful)

Create `~/ansible/ansible.cfg` to set project-wide defaults so you do not
have to type `-i inventory/hosts.ini` every time:

```ini
[defaults]
inventory         = inventory/hosts.ini
remote_user       = super90
host_key_checking = False
retry_files_enabled = False

[privilege_escalation]
become        = True
become_method = sudo
become_user   = root
```

With this file in place, from inside `~/ansible/` you can run:
```bash
ansible-playbook playbooks/deploy_oled.yml
# instead of:
ansible-playbook -i inventory/hosts.ini playbooks/deploy_oled.yml
```

> `host_key_checking = False` skips the "are you sure you want to connect?"
> prompt on first SSH. Fine for a trusted home network.

---

## Part 6 — Test Everything

### Ping all Pis
```bash
ansible -i inventory/hosts.ini pis -m ping
```
Expected output for each Pi:
```
mavx_server | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
```

### Run a command on all Pis at once
```bash
# Check OS version on all Pis simultaneously
ansible -i inventory/hosts.ini pis -m shell -a "cat /etc/os-release"

# Check uptime
ansible -i inventory/hosts.ini pis -m shell -a "uptime"

# Check who is logged in
ansible -i inventory/hosts.ini pis -m shell -a "whoami" --become
```

### Target a single Pi
```bash
ansible -i inventory/hosts.ini mavx_server -m ping
```

### Target a specific Pi by IP instead of alias
```bash
ansible -i inventory/hosts.ini 192.168.1.175 -m ping
```

---

## Part 7 — Understanding Playbooks

A playbook is a YAML file that describes a sequence of tasks to run on your
hosts. Here is the simplest possible example:

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

    - name: Print a message
      debug:
        msg: "Hello from {{ inventory_hostname }} ({{ ansible_host }})"
```

Run it with:
```bash
ansible-playbook -i inventory/hosts.ini playbooks/my_first.yml
```

### Key playbook concepts

**`hosts:`** — which group or host to run against. `pis` = all Pis,
`mavx_server` = just that one Pi.

**`become: true`** — run tasks as root via sudo.

**`tasks:`** — ordered list of things to do. Ansible runs them top to bottom.

**Modules** — the built-in actions like `apt`, `copy`, `shell`, `systemd`,
`lineinfile`, `file`, `pip`, `user`. Each module is idempotent — running it
twice has the same result as running it once.

**`notify` / `handlers`** — a task can notify a handler (e.g. "restart
service") which only runs once at the end of the play, even if notified
multiple times.

---

## Part 8 — Useful Ansible Commands

### Ad-hoc commands (no playbook needed)
```bash
# Install a package on all Pis
ansible pis -m apt -a "name=htop state=present" --become

# Copy a file to all Pis
ansible pis -m copy -a "src=./myfile.conf dest=/etc/myfile.conf" --become

# Restart a service on all Pis
ansible pis -m systemd -a "name=oled-monitor state=restarted" --become

# Reboot all Pis
ansible pis -m reboot --become

# Run a shell command and show output
ansible pis -m shell -a "df -h" --become
```

### Playbook flags
```bash
# Dry run — show what WOULD change without changing anything
ansible-playbook playbooks/deploy_oled.yml --check

# Show full diff of file changes
ansible-playbook playbooks/deploy_oled.yml --diff

# Run only tasks tagged 'deploy'
ansible-playbook playbooks/deploy_oled.yml --tags deploy

# Skip tasks tagged 'install'
ansible-playbook playbooks/deploy_oled.yml --skip-tags install

# Run against one host only
ansible-playbook playbooks/deploy_oled.yml --limit mavx_server

# Verbose output (use -vvv for even more detail)
ansible-playbook playbooks/deploy_oled.yml -v
```

---

## Part 9 — Sudo Without a Password (Recommended)

By default `super90` may need to enter a sudo password. To avoid Ansible
prompting for it, add a passwordless sudo rule on each Pi.

SSH into each Pi and run:
```bash
echo "super90 ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/super90
sudo chmod 440 /etc/sudoers.d/super90
```

Or do it with Ansible itself (you will be prompted for the sudo password
this one last time):
```bash
ansible pis -m shell \
  -a "echo 'super90 ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/super90 && chmod 440 /etc/sudoers.d/super90" \
  --become --ask-become-pass
```

After this, no password prompts ever again.

---

## Part 10 — Troubleshooting

### "Permission denied (publickey)"
Your SSH key is not on the Pi yet. Run:
```bash
ssh-copy-id super90@192.168.1.175
```

### "sudo: a password is required"
Either add `--ask-become-pass` to your command, or set up passwordless sudo
(see Part 9 above).

### "Python not found on remote"
Make sure `ansible_python_interpreter=/usr/bin/python3` is in your
`[pis:vars]` block in `hosts.ini`.

### Host unreachable
Check the Pi is powered on and connected:
```bash
ping 192.168.1.175
```
Then verify SSH works manually:
```bash
ssh super90@192.168.1.175
```

### "CHANGED" showing on every run (not idempotent)
Avoid using the `shell` or `command` module for things that have a proper
Ansible module. Use `apt` instead of `shell: apt install`, use `copy`
instead of `shell: cp`, etc.

---

## Quick Reference Card

```
# Test connectivity
ansible -i inventory/hosts.ini pis -m ping

# Run a playbook
ansible-playbook -i inventory/hosts.ini playbooks/deploy_oled.yml

# Run only deploy tasks
ansible-playbook -i inventory/hosts.ini playbooks/deploy_oled.yml --tags deploy

# Target one Pi
ansible-playbook -i inventory/hosts.ini playbooks/deploy_oled.yml --limit mavx_server

# Dry run
ansible-playbook -i inventory/hosts.ini playbooks/deploy_oled.yml --check

# Ad-hoc shell command on all Pis
ansible -i inventory/hosts.ini pis -m shell -a "uptime" --become

# Check service status on all Pis
ansible -i inventory/hosts.ini pis -m shell -a "systemctl status oled-monitor --no-pager" --become

# View logs from all Pis
ansible -i inventory/hosts.ini pis -m shell -a "journalctl -u oled-monitor -n 20 --no-pager" --become
```
