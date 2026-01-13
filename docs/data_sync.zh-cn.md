## 概述

**这个仓库提供了一个数据同步工具**，用于将本地文件夹与远程服务器进行**单向同步**。工具本质是对 `rsync` 的封装 📦

DPZ 提供了一个 **Samba 服务器** 用于存储同步数据，因此第一步是**挂载 Samba**。

## 挂载 Samba

进入项目目录：`/src/mxbi/tools/sync_data`，然后运行：

```bash
python main.py setup
```

在 `setup` 过程中需要输入 `Samba 地址`、`Domain`、`用户名`、`密码` 等信息。

脚本会创建一个 `systemd` 服务用于自动挂载 Samba，并通过 `systemd-creds` 加密保存你的密钥 🔐

挂载路径如下：

```python
SAMBA_MOUNT_PATH = ROOT_DIR_PATH / "samba_mount"
```

## 触发同步

完成 `setup` 后，只需在 Python 中调用 `sync_data()` 即可同步：

```python
from mxbi.tools.sync_data.sync_data import sync_data

sync_data()
```

`sync_data` 会将本地项目根目录下的 `data` 目录与 Samba 服务器进行同步 ✅
