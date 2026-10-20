"""Fetch the actual HA constraints and integration requirements for CI."""

import argparse
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("tag")
parser.add_argument("directory", type=Path)
args = parser.parse_args()
args.directory.mkdir(parents=True, exist_ok=True)
base = "https://api.github.com/repos/home-assistant/core/contents/homeassistant"


def fetch(path: str) -> str:
    headers = {"Accept": "application/vnd.github.raw+json"}
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"{base}/{path}?ref={args.tag}", headers=headers)
    with urlopen(request, timeout=30) as response:
        return response.read().decode()


constraints = fetch("package_constraints.txt")
requirements = json.loads(fetch("components/modbus/manifest.json"))["requirements"]
# Exercise the ESPHome transport with the version HA actually installs, too.
esphome = json.loads(fetch("components/esphome/manifest.json"))["requirements"]
requirements += [
    requirement for requirement in esphome if requirement.startswith("aioesphomeapi==")
]
(args.directory / "constraints.txt").write_text(constraints)
(args.directory / "requirements.txt").write_text("\n".join(requirements) + "\n")
print(f"Home Assistant {args.tag}: {requirements}")
print(next(line for line in constraints.splitlines() if line.startswith("serialx==")))
