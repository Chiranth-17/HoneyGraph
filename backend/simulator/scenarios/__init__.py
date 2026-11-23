"""Abstract defensive attack-chain scenarios."""

from . import credential_stuffing, exfil_burst, lateral_movement, log_tamper, mirai_bruteforce, mqtt_abuse, recon

SCENARIOS = {
    "mirai_bruteforce": mirai_bruteforce.generate,
    "recon": recon.generate,
    "credential_stuffing": credential_stuffing.generate,
    "mqtt_abuse": mqtt_abuse.generate,
    "lateral_movement": lateral_movement.generate,
    "exfil_burst": exfil_burst.generate,
    "log_tamper": log_tamper.generate,
}

