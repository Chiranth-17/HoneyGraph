 """Generate deterministic virtual IoT inventory around Bengaluru."""

from __future__ import annotations

import random
from typing import Any

from pymongo import ReplaceOne
from pymongo.database import Database

DEVICE_TYPES = ("camera", "energy_meter", "signal_controller", "environmental_sensor")
PROTOCOLS = ("mqtt", "coap", "http", "ssh", "telnet")
FIRMWARE = {
    "camera": ("cam-os-2.4.1", "cam-os-2.5.0"),
    "energy_meter": ("meter-fw-1.8.2", "meter-fw-1.9.0"),
    "signal_controller": ("signal-rt-4.2", "signal-rt-4.3"),
    "environmental_sensor": ("env-fw-3.1", "env-fw-3.2"),
}
ATTACKER_NETWORKS = ("192.0.2", "198.51.100", "203.0.113")


def generate_devices(count: int = 500, seed: int = 42) -> list[dict[str, Any]]:
    """Return reproducible RFC1918 devices with Bengaluru GeoJSON points."""
    rng = random.Random(seed)
    devices: list[dict[str, Any]] = []
    for index in range(count):
        kind = DEVICE_TYPES[index % len(DEVICE_TYPES)]
        protocol = PROTOCOLS[index % len(PROTOCOLS)]
        third_octet, host = divmod(index, 250)
        baseline = rng.randint(700, 6_000)
        devices.append(
            {
                "deviceId": f"blr-{kind.replace('_', '-')}-{index + 1:04d}",
                "ip": f"10.42.{third_octet}.{host + 1}",
                "type": kind,
                "firmware": rng.choice(FIRMWARE[kind]),
                "protocol": protocol,
                "location": {
                    "type": "Point",
                    "coordinates": [round(77.5946 + rng.uniform(-0.18, 0.18), 6), round(12.9716 + rng.uniform(-0.14, 0.14), 6)],
                },
                "baseline": {"bytesOut": baseline},
            }
        )
    return devices


def attacker_ips(count: int, seed: int) -> list[str]:
    """Return documentation-only RFC5737 addresses."""
    rng = random.Random(seed)
    addresses = [f"{network}.{host}" for network in ATTACKER_NETWORKS for host in range(1, 255)]
    rng.shuffle(addresses)
    return addresses[:count]


def upsert_devices(db: Database[Any], devices: list[dict[str, Any]]) -> None:
    if not devices:
        return
    operations = [ReplaceOne({"deviceId": item["deviceId"]}, item, upsert=True) for item in devices]
    db.devices.bulk_write(operations, ordered=False)

