# File : hints.py
# Author : Sébastien Deriaz
# License : GPL
"""
Advice appended to error messages, so that an error says what to do about it
"""

from __future__ import annotations

import os
import stat
import sys

# Group usually given to each kind of device file, and the udev name pattern
_DEVICE_GROUPS = (
    ("i2c-", "i2c", 'KERNEL=="i2c-[0-9]*"'),
    ("spidev", "spi", 'KERNEL=="spidev*"'),
    ("tty", "dialout", 'KERNEL=="{name}"'),
)


def permission_hint(path: str) -> str:
    """
    What to do when the user may not open a device file, empty if there is no advice

    On Linux the answer is a group : the one that owns the file if there is one, a udev
    rule giving it one otherwise. On Windows "access denied" on a port means another
    program has it open
    """
    if sys.platform == "win32":
        return busy_hint(path)
    try:
        info = os.stat(path)
    except OSError:
        return ""

    name = os.path.basename(path)
    group = _group_name(info.st_gid)
    group_can_use = bool(info.st_mode & stat.S_IRGRP and info.st_mode & stat.S_IWGRP)

    if group_can_use and group != "root":
        if info.st_gid in os.getgroups():
            return (
                f"Your user is in the group '{group}' that owns {path}, but this "
                "session started before it was added : log out and back in (or reboot)"
            )
        return (
            f"{path} belongs to the group '{group}'. Add your user to it, then log out "
            f"and back in :\n    sudo usermod -aG {group} $USER"
        )

    suggested, pattern = "dialout", f'KERNEL=="{name}"'
    for prefix, candidate, udev_pattern in _DEVICE_GROUPS:
        if name.startswith(prefix):
            suggested, pattern = candidate, udev_pattern.format(name=name)
            break
    return (
        f"Only root may open {path}. Give it a group with a udev rule, in "
        f"/etc/udev/rules.d/99-syndesi.rules :\n"
        f'    {pattern}, GROUP="{suggested}", MODE="0660"\n'
        "then add your user to that group, and log out and back in :\n"
        f"    sudo groupadd -f {suggested}\n"
        f"    sudo usermod -aG {suggested} $USER\n"
        "    sudo udevadm control --reload-rules && sudo udevadm trigger"
    )


def busy_hint(path: str) -> str:
    """Advice for a port another program holds"""
    return (
        f"{path} is probably open in another program (serial monitor, terminal, "
        "another script...) : close it and try again"
    )


def _group_name(gid: int) -> str:
    try:
        import grp  # pylint: disable=import-outside-toplevel  # Unix only

        return grp.getgrgid(gid).gr_name
    except (ImportError, KeyError):
        return str(gid)
