import json
import requests


def service_ip_range(service: str, region: str):
    aws_ip_ranges = json.loads(
        requests.get("https://ip-ranges.amazonaws.com/ip-ranges.json").text
    )

    for entry in aws_ip_ranges["prefixes"]:
        if entry["service"] == service and entry["region"] == region:
            return entry["ip_prefix"]

    raise NameError
