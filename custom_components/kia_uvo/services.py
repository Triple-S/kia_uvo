import logging
from datetime import datetime
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry
from hyundai_kia_connect_api import (
    ClimateRequestOptions,
    POICoord,
    POIInfo,
    ScheduleChargingClimateRequestOptions,
    WindowRequestOptions,
)

from .const import DOMAIN, OffPeakChargingMode
from .coordinator import HyundaiKiaConnectDataUpdateCoordinator

SERVICE_UPDATE = "update"
SERVICE_FORCE_UPDATE = "force_update"
SERVICE_SET_NAVIGATION = "set_navigation"
SERVICE_CAPTURE_SVM_IMAGE = "capture_svm_image"

SUPPORTED_SERVICES = (
    SERVICE_UPDATE,
    SERVICE_FORCE_UPDATE,
    SERVICE_SET_NAVIGATION,
    SERVICE_CAPTURE_SVM_IMAGE,
)

_LOGGER = logging.getLogger(__name__)


@callback
def async_setup_services(hass: HomeAssistant) -> bool:
    """Set up services for Hyundai Kia Connect"""

    async def async_handle_force_update(call: ServiceCall) -> None:
        coordinator = _get_coordinator_from_device(hass, call)
        await coordinator.async_force_update(_get_vehicle_id_from_device(hass, call) if ATTR_DEVICE_ID in call.data else None)

    async def async_handle_update(call: ServiceCall) -> None:
        _LOGGER.debug(f"Call:{call.data}")
        coordinator = _get_coordinator_from_device(hass, call)
        await coordinator.async_update(_get_vehicle_id_from_device(hass, call) if ATTR_DEVICE_ID in call.data else None)

    async def async_handle_set_navigation(call: ServiceCall) -> None:
        coordinator = _get_coordinator_from_device(hass, call)
        vehicle_id = _get_vehicle_id_from_device(hass, call)
        latitude = call.data["latitude"]
        longitude = call.data["longitude"]
        name = call.data["name"]
        address = call.data.get("address", "")
        zip_code = call.data.get("zip_code", "")
        place_id = call.data.get("place_id", "")

        poi = POIInfo(
            coord=POICoord(lat=float(latitude), lon=float(longitude)),
            name=name,
            addr=address,
            zip=zip_code,
            place_id=place_id,
        )
        await coordinator.async_set_navigation(vehicle_id, [poi])

    async def async_handle_capture_svm_image(call: ServiceCall) -> None:
        coordinator = _get_coordinator_from_device(hass, call)
        vehicle_id = _get_vehicle_id_from_device(hass, call)

        if not await coordinator.async_supports_svm(vehicle_id):
            raise HomeAssistantError("SVM is not available for this vehicle.")

        await coordinator.async_request_svm_capture(vehicle_id)

    services = {
        SERVICE_FORCE_UPDATE: async_handle_force_update,
        SERVICE_UPDATE: async_handle_update,
        SERVICE_SET_NAVIGATION: async_handle_set_navigation,
        SERVICE_CAPTURE_SVM_IMAGE: async_handle_capture_svm_image,
    }

    for service in SUPPORTED_SERVICES:
        hass.services.async_register(DOMAIN, service, services[service])
    return True


@callback
def async_unload_services(hass: HomeAssistant) -> None:
    for service in SUPPORTED_SERVICES:
        hass.services.async_remove(DOMAIN, service)


def _get_vehicle_id_from_device(hass: HomeAssistant, call: ServiceCall) -> str:
    coordinators = list(hass.data[DOMAIN].keys())
    if len(coordinators) == 1:
        coordinator = cast(
            HyundaiKiaConnectDataUpdateCoordinator, hass.data[DOMAIN][coordinators[0]]
        )
        vehicles = coordinator.vehicle_manager.vehicles
        if len(vehicles) == 1:
            return cast(str, next(iter(vehicles.keys())))

    device_entry = device_registry.async_get(hass).async_get(call.data[ATTR_DEVICE_ID])
    if device_entry is None:
        raise HomeAssistantError(f"Device {call.data[ATTR_DEVICE_ID]} not found")
    for entry in device_entry.identifiers:
        if entry[0] == DOMAIN:
            vehicle_id = entry[1]
    return vehicle_id


def _get_coordinator_from_device(
    hass: HomeAssistant, call: ServiceCall
) -> HyundaiKiaConnectDataUpdateCoordinator:
    coordinators = list(hass.data[DOMAIN].keys())
    if len(coordinators) == 1:
        return cast(
            HyundaiKiaConnectDataUpdateCoordinator, hass.data[DOMAIN][coordinators[0]]
        )
    else:
        device_entry = device_registry.async_get(hass).async_get(
            call.data[ATTR_DEVICE_ID]
        )
        if device_entry is None:
            raise HomeAssistantError(f"Device {call.data[ATTR_DEVICE_ID]} not found")
        config_entry_ids = device_entry.config_entries
        config_entry_id = next(
            (
                config_entry_id
                for config_entry_id in config_entry_ids
                if cast(
                    ConfigEntry,
                    hass.config_entries.async_get_entry(config_entry_id),
                ).domain
                == DOMAIN
            ),
            None,
        )
        if config_entry_id is None:
            raise HomeAssistantError(
                f"No {DOMAIN} config entry found for device {call.data[ATTR_DEVICE_ID]}"
            )
        config_entry = hass.config_entries.async_get_entry(config_entry_id)
        if config_entry is None:
            raise HomeAssistantError(f"Config entry {config_entry_id} not found")
        config_entry_unique_id = config_entry.unique_id
        return cast(
            HyundaiKiaConnectDataUpdateCoordinator,
            hass.data[DOMAIN][config_entry_unique_id],
        )
