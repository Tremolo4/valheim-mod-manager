from datetime import datetime
from pathlib import Path
from typing import Optional, Union
import logging

# TODO: only import on windows
import winreg


def find_steam_install_path(appid: str) -> Optional[Path]:
    """Query the Windows Registry to find the Steam Valheim installation directory"""
    logging.debug("Looking for Valheim directory in Windows Registry")
    registry = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
    try:
        key = winreg.OpenKey(
            registry,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App "
            + str(appid),
            access=winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        )
        (value, type) = winreg.QueryValueEx(key, "InstallLocation")
        if type == winreg.REG_SZ:
            logging.info(f"Discovered Valheim directory: {str(value)}")
            return Path(value)
    except FileNotFoundError:
        logging.warning("Could not find Valheim directory in registry.")


def ts_to_text(timestamp: Union[int, None]) -> str:
    if timestamp is None:
        return "unknown"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


# based on https://stackoverflow.com/a/1551394
def pretty_date(time: Union[int, datetime, None]) -> str:
    """
    Get a datetime object or a int() Epoch timestamp and return a
    pretty string like 'an hour ago', 'Yesterday', '3 months ago',
    'just now', etc
    """
    if time is None:
        return "unknown"

    from datetime import datetime

    now = datetime.now()
    if type(time) is int:
        diff = now - datetime.fromtimestamp(time)
    elif isinstance(time, datetime):
        diff = now - time
    else:
        diff = now - now
    second_diff = diff.seconds
    day_diff = diff.days

    if day_diff < 0:
        return ""

    if day_diff == 0:
        if second_diff < 10:
            return "just now"
        if second_diff < 60:
            return f"{(second_diff):.0f} seconds ago"
        if second_diff < 120:
            return "a minute ago"
        if second_diff < 3600:
            return f"{(second_diff / 60):.0f} minutes ago"
        if second_diff < 7200:
            return "an hour ago"
        if second_diff < 86400:
            return f"{(second_diff / 3600):.0f} hours ago"
    if day_diff == 1:
        return "Yesterday"
    if day_diff < 7:
        return f"{day_diff} days ago"
    if day_diff < 31:
        return f"{(day_diff / 7):.1f} weeks ago"
    if day_diff < 365:
        return f"{(day_diff / 30):.1f} months ago"
    return f"{(day_diff / 365):.1f} years ago"


def thunderstore_date_to_ts(date_string):
    return int(datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp())
