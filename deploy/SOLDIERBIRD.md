# Deployment

## Local dev (Windows)
```
dev
```
From `finance/` root → http://localhost:8003

---

## Build & push image (WSL - local)

First time only — enable ARM64 emulation in WSL:
```bash
sudo apt-get install -y qemu-user-static binfmt-support
```

Each release:
```bash
cd /mnt/c/Users/tim/PycharmProjects/finance
podman build --platform linux/arm64 -t docker.io/divepeak/finance:latest .
podman login docker.io
podman push docker.io/divepeak/finance:latest
```
> First build is slow (~15 min) due to Playwright/Chromium. Subsequent builds are fast if
> `pyproject.toml` / `uv.lock` haven't changed.

---

## First-time Pi setup

**WSL - local:** copy the database and Quadlet service file:
```bash
cd /mnt/c/Users/tim/PycharmProjects/finance
rsync -avz database_v2.db tim@192.168.68.83:/srv/finance/finance.db
rsync -avz deploy/finance.container tim@192.168.68.83:/home/tim/.config/containers/systemd/
```

**WSL - Pi (ssh tim@192.168.68.83):** pull the image and start the service:
```bash
mkdir -p /srv/finance
mkdir -p ~/.config/containers/systemd
podman pull docker.io/divepeak/finance:latest
systemctl --user daemon-reload
systemctl --user start finance.service
loginctl enable-linger tim          # run once — allows service to start without login
```

App is available at http://192.168.68.83:8003

---

## Update

**WSL - local:** build, push, and restart:
```bash
cd /mnt/c/Users/tim/PycharmProjects/finance
podman build --platform linux/arm64 -t docker.io/divepeak/finance:latest .
podman push docker.io/divepeak/finance:latest
```

**WSL - Pi:** pull and restart:
```bash
podman pull docker.io/divepeak/finance:latest
systemctl --user restart finance.service
```

---

## Useful Pi commands

```bash
systemctl --user status finance.service
journalctl --user -u finance.service -f
systemctl --user restart finance.service
podman ps
```
