# File : system.py
# Author : Sébastien Deriaz
# License : GPL
"""
Light or dark, as chosen in the settings of the system, and its changes
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import SLOT, QObject, Qt, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
)

# The desktop portal publishes the light / dark preference of GNOME, KDE, ... Qt only
# reads it with its xdgdesktopportal platform theme : on GNOME it picks gtk3, which
# derives the scheme from the GTK theme name ("Adwaita", light) and ignores the setting
_PORTAL_SERVICE = "org.freedesktop.portal.Desktop"
_PORTAL_PATH = "/org/freedesktop/portal/desktop"
_PORTAL_SETTINGS = "org.freedesktop.portal.Settings"
_APPEARANCE = ("org.freedesktop.appearance", "color-scheme")


def _unwrap(value: Any) -> Any:
    # ReadOne returns a variant, the older Read a variant of a variant
    while hasattr(value, "variant"):
        value = value.variant()
    return value


def _scheme_is_dark(value: Any) -> bool | None:
    """Portal color-scheme : 1 dark, 2 light, 0 no preference (the light default)"""
    value = _unwrap(value)
    if value in (0, 1, 2):
        return bool(value == 1)
    return None


def portal_prefers_dark() -> bool | None:
    """Preference published by the desktop portal, None where there is no portal"""
    try:
        from PySide6.QtDBus import (  # pylint: disable=import-outside-toplevel
            QDBus,
            QDBusConnection,
            QDBusMessage,
        )
    except ImportError:
        return None
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return None
    message = QDBusMessage.createMethodCall(
        _PORTAL_SERVICE, _PORTAL_PATH, _PORTAL_SETTINGS, "ReadOne"
    )
    message.setArguments(list(_APPEARANCE))
    reply = bus.call(message, QDBus.CallMode.Block, 500)
    if reply.type() != QDBusMessage.MessageType.ReplyMessage or not reply.arguments():
        return None
    return _scheme_is_dark(reply.arguments()[0])


def system_prefers_dark() -> bool:
    """Light or dark, as chosen in the settings of the system"""
    portal = portal_prefers_dark()
    if portal is not None:
        return portal
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


class SystemWatcher(QObject):
    """
    Follows the light / dark setting of the system while the application runs, and
    calls on_change(dark) when it changes
    """

    def __init__(self, app: QApplication, on_change: Callable[[bool], None]) -> None:
        super().__init__(app)
        self._on_change = on_change
        self._dark = system_prefers_dark()
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._qt_changed)
        try:
            from PySide6.QtDBus import QDBusConnection  # pylint: disable=import-outside-toplevel
        except ImportError:
            return
        bus = QDBusConnection.sessionBus()
        if bus.isConnected():
            bus.connect(  # type: ignore[call-overload]
                "",
                _PORTAL_PATH,
                _PORTAL_SETTINGS,
                "SettingChanged",
                self,
                SLOT("_portal_changed(QDBusMessage)"),
            )

    @Slot(object)
    def _qt_changed(self, _: Any = None) -> None:
        self._set(system_prefers_dark())

    @Slot("QDBusMessage")
    def _portal_changed(self, message: Any) -> None:
        arguments = message.arguments()
        if tuple(arguments[:2]) == _APPEARANCE and len(arguments) > 2:
            dark = _scheme_is_dark(arguments[2])
            if dark is not None:
                self._set(dark)

    def _set(self, dark: bool) -> None:
        if dark != self._dark:
            self._dark = dark
            self._on_change(dark)
