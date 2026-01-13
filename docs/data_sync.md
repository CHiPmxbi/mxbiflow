## Overview

**This repository provides a data synchronization tool** used to perform **one-way synchronization** between a local folder and a remote server. The tool is essentially a wrapper around `rsync` 📦

DPZ provides a **Samba server** for storing synchronized data, so the first step is to **mount the Samba share**.

## Mount Samba

Enter the project directory: `/src/mxbi/tools/sync_data`, then run:

```bash
python main.py setup
```

During `setup`, you need to enter the `Samba address`, `Domain`, `username`, `password`, and other information.

The script will create a `systemd` service for automatically mounting Samba, and it will store your credentials encrypted via `systemd-creds` 🔐

The mount path is:

```python
SAMBA_MOUNT_PATH = ROOT_DIR_PATH / "samba_mount"
```

## Trigger Sync

After `setup`, simply call `sync_data()` in Python to sync:

```python
from mxbi.tools.sync_data.sync_data import sync_data

sync_data()
```

`sync_data` will synchronize the `data` directory under the local project root with the Samba server ✅
