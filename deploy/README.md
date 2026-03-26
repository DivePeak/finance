# Deployment

## Local dev
```
dev
```
From `finance/` root → http://localhost:8003

---

## Build & push image (WSL)

First time only — enable ARM64 emulation in WSL:
```bash
sudo apt-get install -y qemu-user-static binfmt-support
sudo update-binfmts --install qemu-aarch64 /usr/bin/qemu-aarch64-static \
    --magic '\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\xb7\x00' \
    --mask '\xff\xff\xff\xff\xff\xff\xff\x00\xff\xff\xff\xff\xff\xff\xff\xff\xfe\xff\xff\xff' \
    --credentials yes --fix-binary yes
```

Each release:
```bash
cd /path/to/finance
podman login docker.io
podman build --platform linux/arm64 -t docker.io/<your-username>/finance:latest .
podman push docker.io/<your-username>/finance:latest
```
> First build is slow (~15 min) due to Playwright/Chromium. Subsequent builds are fast if
> `pyproject.toml` / `uv.lock` haven't changed.

---

## First-time Pi setup

**Local:** copy the database and Quadlet service file:
```bash
rsync -avz database_v2.db <user>@<pi-ip>:/srv/finance/finance.db
rsync -avz deploy/finance.container <user>@<pi-ip>:/home/<user>/.config/containers/systemd/
```

**Pi (via SSH):** pull the image and start the service:
```bash
mkdir -p /srv/finance
sudo chown <user>:<user> /srv/finance
mkdir -p ~/.config/containers/systemd
podman pull docker.io/<your-username>/finance:latest
systemctl --user daemon-reload
systemctl --user start finance.service
loginctl enable-linger <user>          # run once — allows service to start without login
```

Update `finance.container` with your Docker Hub username and data path before deploying.

---

## Update

**Local:**
```bash
podman build --platform linux/arm64 -t docker.io/<your-username>/finance:latest .
podman push docker.io/<your-username>/finance:latest
```

**Pi:**
```bash
podman pull docker.io/<your-username>/finance:latest
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
