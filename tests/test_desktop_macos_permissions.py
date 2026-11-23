"""Guardrails for the macOS desktop build's permission declarations.

Two independent files have to agree before macOS will let the app touch the
microphone:

  * ``desktop/build/entitlements.mac.plist`` (wired to ``mac.entitlements`` and
    ``mac.entitlementsInherit``) decides whether the permission dialog may be
    shown at all. Under Hardened Runtime, a missing
    ``com.apple.security.device.audio-input`` makes tccd answer
    "Policy disallows prompt": no dialog, no TCC record, and the app never
    appears in System Settings -> Privacy & Security.
  * ``desktop/package.json`` ``build.mac.extendInfo`` decides only what the
    dialog *says*, but a device permission with no usage description is
    rejected by macOS as well.

Both failures are silent at runtime -- the user just sees a mic button that
does nothing -- so nothing catches a regression except a test like this one.

Deliberately dumb on purpose: these are packaging-config assertions, not a
reimplementation of electron-builder or of Apple's TCC policy.
"""

import json
import plistlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DESKTOP_DIR = REPO_ROOT / "desktop"
ENTITLEMENTS_PATH = DESKTOP_DIR / "build" / "entitlements.mac.plist"
PACKAGE_JSON_PATH = DESKTOP_DIR / "package.json"

# Device entitlements that Hardened Runtime requires before tccd will prompt.
REQUIRED_DEVICE_ENTITLEMENTS = (
    "com.apple.security.device.audio-input",
    "com.apple.security.device.camera",
)

# Info.plist keys macOS requires alongside the entitlements above. Without a
# description the request is denied even when the entitlement is present.
REQUIRED_USAGE_DESCRIPTIONS = (
    "NSMicrophoneUsageDescription",
    "NSCameraUsageDescription",
)


def _load_entitlements() -> dict:
    assert ENTITLEMENTS_PATH.is_file(), f"missing {ENTITLEMENTS_PATH}"
    with ENTITLEMENTS_PATH.open("rb") as fh:
        return plistlib.load(fh)


def _load_mac_config() -> dict:
    assert PACKAGE_JSON_PATH.is_file(), f"missing {PACKAGE_JSON_PATH}"
    package = json.loads(PACKAGE_JSON_PATH.read_text(encoding="utf-8"))
    return package["build"]["mac"]


def test_entitlements_file_is_valid_plist():
    entitlements = _load_entitlements()
    assert isinstance(entitlements, dict)
    # Sanity: the Electron/PyInstaller keys the build already relied on.
    assert entitlements["com.apple.security.cs.allow-jit"] is True
    assert entitlements["com.apple.security.cs.disable-library-validation"] is True


@pytest.mark.parametrize("key", REQUIRED_DEVICE_ENTITLEMENTS)
def test_device_entitlements_are_declared(key):
    entitlements = _load_entitlements()
    assert entitlements.get(key) is True, (
        f"{key} is missing from entitlements.mac.plist; macOS will refuse to "
        "prompt for this device under Hardened Runtime"
    )


@pytest.mark.parametrize("key", REQUIRED_USAGE_DESCRIPTIONS)
def test_usage_descriptions_are_declared(key):
    mac = _load_mac_config()
    extend_info = mac.get("extendInfo") or {}
    description = extend_info.get(key)
    # Apple rejects an empty usage description, so require real text.
    assert isinstance(description, str) and description.strip(), (
        f"{key} is missing or empty in package.json build.mac.extendInfo"
    )


def test_entitlements_file_is_wired_into_the_signing_config():
    """The plist only matters if electron-builder is pointed at it."""
    mac = _load_mac_config()
    assert mac["hardenedRuntime"] is True
    for field in ("entitlements", "entitlementsInherit"):
        assert mac[field] == "build/entitlements.mac.plist", (
            f"build.mac.{field} no longer points at entitlements.mac.plist"
        )
