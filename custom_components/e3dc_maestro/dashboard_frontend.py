"""Register the Lovelace community dashboard strategy with Home Assistant."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import (
    CONF_RESOURCE_TYPE_WS,
    DOMAIN as LOVELACE_DOMAIN,
)
from homeassistant.components.lovelace.resources import (
    ResourceStorageCollection,
    ResourceYAMLCollection,
)
from homeassistant.const import CONF_ID, CONF_URL
from homeassistant.core import HomeAssistant

from .const import DOMAIN, VERSION

_LOGGER = logging.getLogger(__name__)

_FRONTEND_DIR = Path(__file__).parent / "frontend"
_STRATEGY_JS = "e3dc-maestro-strategy.js"
_STATIC_URL_BASE = f"/{DOMAIN}/frontend"
_SETUP_FLAG = f"{DOMAIN}_frontend_registered"
_YAML_WARNED = f"{DOMAIN}_strategy_yaml_warned"


def _strategy_module_url() -> str:
    # Bust caches when the integration version changes.
    return f"{_STATIC_URL_BASE}/{_STRATEGY_JS}?v={VERSION}"


def _strategy_module_path(url: str) -> str:
    return url.split("?", 1)[0]


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Serve strategy assets, preload the JS module, and register a Lovelace resource."""
    module_url = _strategy_module_url()
    if not hass.data.get(_SETUP_FLAG):
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    _STATIC_URL_BASE,
                    str(_FRONTEND_DIR),
                    cache_headers=False,
                )
            ]
        )
        add_extra_js_url(hass, module_url)
        hass.data[_SETUP_FLAG] = True
        _LOGGER.debug("Registered E3DC Maestro dashboard strategy at %s", module_url)

    # Lovelace waits only 5s for ll-strategy-dashboard-* to be defined. Extra JS
    # in index.html is often missing from a cached frontend; a dashboard resource
    # is the documented load path and is fetched when Lovelace starts.
    await _async_register_lovelace_resource(hass, module_url)


def _lovelace_resources(hass: HomeAssistant):
    lovelace_data = hass.data.get(LOVELACE_DOMAIN)
    if lovelace_data is None:
        return None
    resources = getattr(lovelace_data, "resources", None)
    if resources is None and isinstance(lovelace_data, dict):
        return lovelace_data.get("resources")
    return resources


async def _async_register_lovelace_resource(hass: HomeAssistant, module_url: str) -> None:
    """Ensure the strategy JS is a Lovelace JavaScript module resource."""
    resources = _lovelace_resources(hass)
    if not resources:
        _LOGGER.debug(
            "Lovelace resources not available; strategy relies on extra JS until restart"
        )
        return

    if isinstance(resources, ResourceStorageCollection) and not resources.loaded:
        await resources.async_load()
        resources.loaded = True

    module_path = _strategy_module_path(module_url)
    existing = None
    for item in resources.async_items():
        item_url = str(item.get(CONF_URL) or "")
        if _strategy_module_path(item_url) == module_path:
            existing = item
            break

    if existing is not None:
        if (
            existing.get(CONF_URL) != module_url
            and isinstance(resources, ResourceStorageCollection)
        ):
            await resources.async_update_item(
                existing[CONF_ID],
                {CONF_RESOURCE_TYPE_WS: "module", CONF_URL: module_url},
            )
            _LOGGER.debug(
                "Updated E3DC Maestro Lovelace strategy resource to %s", module_url
            )
        return

    if isinstance(resources, ResourceYAMLCollection):
        if not hass.data.get(_YAML_WARNED):
            hass.data[_YAML_WARNED] = True
            _LOGGER.warning(
                "Lovelace resources are in YAML mode; add this module so the Maestro "
                "dashboard strategy can load:\n  - url: %s\n    type: module",
                module_url,
            )
        return

    if not isinstance(resources, ResourceStorageCollection):
        return

    await resources.async_create_item(
        {CONF_RESOURCE_TYPE_WS: "module", CONF_URL: module_url}
    )
    _LOGGER.info("Registered E3DC Maestro Lovelace strategy resource %s", module_url)
