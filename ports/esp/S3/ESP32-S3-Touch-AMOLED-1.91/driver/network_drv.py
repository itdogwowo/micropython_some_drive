from lib.sys_bus import bus
from lib.network_manager import NetworkManager


def config():
    nm = bus.get_service("network_manager")
    if nm is not None:
        return nm
    nm = NetworkManager(bus)
    bus.register_service("network_manager", nm)
    return nm
