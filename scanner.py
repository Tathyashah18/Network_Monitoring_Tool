
import os
import sys
import re
import json
import ipaddress
import subprocess

from concurrent.futures import ThreadPoolExecutor, as_completed
from django.db import transaction

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nms.settings")

import django
django.setup()

from django.utils import timezone
from dashboard.models import Device, DeviceLog, DeviceStats, DeviceStatsHistory


MAX_WORKERS = 30
PING_TIMEOUT_MS = 1000
POWERSHELL_TIMEOUT_SECONDS = 60


def get_networks():
    print("\n[NETWORK] Detecting active network interfaces...")

    script = r"""
    $results = @()
    $adapters = Get-NetAdapter -ErrorAction Stop | Where-Object {
        $_.Status -eq 'Up' -and (
            $_.Name -eq 'Wi-Fi' -or
            $_.InterfaceDescription -match 'Wi-Fi Direct|Wireless|802\.11'
        )
    }

    foreach ($adapter in $adapters) {
        $addresses = Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
        foreach ($address in $addresses) {
            if ($address.IPAddress -like '169.254.*' -or $address.IPAddress -eq '127.0.0.1') {
                continue
            }

            $results += [PSCustomObject]@{
                InterfaceAlias = $adapter.Name
                InterfaceDescription = $adapter.InterfaceDescription
                InterfaceIndex = $adapter.ifIndex
                IPAddress = $address.IPAddress
                PrefixLength = $address.PrefixLength
            }
        }
    }
    ConvertTo-Json -InputObject $results -Compress
    """

    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=POWERSHELL_TIMEOUT_SECONDS,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())

        output = result.stdout.strip()
        if not output:
            raise RuntimeError("No active Wi-Fi networks found.")

        data = json.loads(output)
        if isinstance(data, dict):
            data = [data]

        networks = []
        seen = set()

        for adapter in data:
            local_ip = adapter.get("IPAddress")
            if not local_ip:
                continue

            interface = ipaddress.ip_interface(
                f"{local_ip}/{int(adapter.get('PrefixLength', 24))}"
            )
            network = interface.network
            key = (adapter.get("InterfaceIndex"), str(network))

            if key in seen or network.is_loopback or network.is_link_local:
                continue

            seen.add(key)
            networks.append({
                "interface": adapter.get("InterfaceAlias"),
                "description": adapter.get("InterfaceDescription"),
                "interface_index": adapter.get("InterfaceIndex"),
                "local_ip": local_ip,
                "network": network
            })

        if not networks:
            raise RuntimeError("No suitable Wi-Fi networks detected.")

        return networks

    except subprocess.TimeoutExpired:
        raise RuntimeError("Windows adapter detection timed out.")
    except Exception as e:
        raise RuntimeError(f"Network detection failed: {e}")


def ping_device(ip):
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", str(PING_TIMEOUT_MS), ip],
            capture_output=True,
            text=True,
            timeout=4,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        output = result.stdout.lower()

        if "reply from" not in output or "destination host unreachable" in output:
            return False, 0

        match = re.search(r"time[=<]\s*(\d+)\s*ms", output)

        if match:
            latency = float(match.group(1))
        elif "<1ms" in output:
            latency = 0.5
        else:
            latency = 0

        return True, latency

    except subprocess.TimeoutExpired:
        return False, 0
    except Exception as e:
        print(f"[PING ERROR] {ip}: {e}")
        return False, 0


def get_arp_table():
    arp_table = {}

    try:
        result = subprocess.run(
            ["arp", "-a"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        for line in result.stdout.splitlines():
            match = re.search(
                r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]{17})",
                line
            )

            if match:
                ip = match.group(1)
                mac = match.group(2).replace("-", ":").lower()

                if mac != "00:00:00:00:00:00":
                    arp_table[ip] = mac

    except Exception as e:
        print(f"[ARP ERROR] {e}")

    return arp_table


def get_hostname(ip):
    try:
        result = subprocess.run(
            ["nslookup", ip],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        for line in result.stdout.splitlines():
            if "name =" in line.lower():
                return line.split("=", 1)[1].strip().rstrip(".")

    except Exception:
        pass

    return None


def update_device(ip, hostname, mac_address):
    now = timezone.now()

    with transaction.atomic():
        device, created = Device.objects.get_or_create(
            ip_address=ip,
            defaults={
                "hostname": hostname,
                "mac_address": mac_address,
                "status": "Online",
                "online_since": now,
                "last_seen": now,
                "last_uptime_seconds": 0
            }
        )

        if created:
            DeviceLog.objects.create(
                device=device,
                status="Online",
                message="New device detected"
            )
            return device

        was_offline = device.status != "Online"

        if hostname:
            device.hostname = hostname

        if mac_address:
            device.mac_address = mac_address

        device.status = "Online"
        device.last_seen = now

        if was_offline:
            device.online_since = now
            device.last_uptime_seconds = 0

            DeviceLog.objects.create(
                device=device,
                status="Online",
                message="Device came back online"
            )

        device.save()
        return device


def update_device_stats(device, latency_ms):
    now = timezone.now()

    stats, _ = DeviceStats.objects.get_or_create(device=device)

    stats.packets_sent += 1
    stats.packets_received += 1
    stats.latency_ms = latency_ms
    stats.last_poll_time = now
    stats.save()

    DeviceStatsHistory.objects.create(
        device=device,
        timestamp=now,
        latency_ms=latency_ms,
        packets_sent=1,
        packets_received=1,
        packets_lost=0,
        packet_loss=0
    )


def generate_ips(network):
    return [str(ip) for ip in network.hosts()]


def scan_single_network(network_info):
    interface = network_info["interface"]
    local_ip = network_info["local_ip"]
    network = network_info["network"]

    print(f"\n{'-' * 40}")
    print(f"[SCANNING] Interface: {interface}")
    print(f"[SCANNING] Local IP : {local_ip}")
    print(f"[SCANNING] Network  : {network}")
    print(f"{'-' * 40}")

    ips = generate_ips(network)
    print(f"Scanning {len(ips)} IP addresses...")

    online_devices = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(ping_device, ip): ip for ip in ips}

        for future in as_completed(futures):
            ip = futures[future]

            try:
                is_online, latency = future.result()

                if is_online:
                    online_devices.append((ip, latency))
                    print(f"[ONLINE] {ip} ({latency} ms)")

            except Exception as e:
                print(f"[ERROR] {ip}: {e}")

    return {
        "interface": interface,
        "local_ip": local_ip,
        "network": network,
        "online_devices": online_devices
    }


def mark_offline_devices(scanned_ips):
    now = timezone.now()

    devices = Device.objects.exclude(status="Offline")

    for device in devices:
        if device.ip_address not in scanned_ips:
            continue

        device.status = "Offline"
        device.save(update_fields=["status"])

        DeviceLog.objects.create(
            device=device,
            status="Offline",
            message="Device did not respond to network scan"
        )


def scan_network():
    print("\n" + "=" * 40)
    print("       MULTI-NETWORK DISCOVERY")
    print("=" * 40)

    try:
        networks = get_networks()
    except Exception as e:
        print(f"\n[NETWORK ERROR] {e}")
        print("[DATABASE] Existing database NOT changed.")
        return

    print("\n[NETWORKS DETECTED]")

    for item in networks:
        print(f"\nInterface : {item['interface']}")
        print(f"Description: {item['description']}")
        print(f"Local IP  : {item['local_ip']}")
        print(f"Network   : {item['network']}")

    all_results = []

    for network_info in networks:
        all_results.append(scan_single_network(network_info))

    arp_table = get_arp_table()
    scanned_ips = set()
    total_online = 0

    for result in all_results:
        network = result["network"]
        print(f"\n[DATABASE] Updating devices from {network}")

        scanned_ips.update(generate_ips(network))

        for ip, latency in result["online_devices"]:
            hostname = get_hostname(ip)
            mac_address = arp_table.get(ip)

            device = update_device(ip, hostname, mac_address)
            update_device_stats(device, latency)
            total_online += 1

    mark_offline_devices(scanned_ips)

    print("\n" + "=" * 40)
    print("       NETWORK DISCOVERY COMPLETE")
    print("=" * 40)

    for result in all_results:
        print(f"\nInterface: {result['interface']}")
        print(f"Network  : {result['network']}")
        print(f"Devices  : {len(result['online_devices'])}")

    print(f"\nTotal online devices: {total_online}")
    print(f"Database devices: {Device.objects.count()}")
    print("Existing historical records preserved.")
    print("Scanner stopped.")
    print("=" * 40)


if __name__ == "__main__":
    scan_network()
