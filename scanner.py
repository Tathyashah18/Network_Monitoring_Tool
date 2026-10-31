import os
import sys
import re
import socket
import subprocess
import ipaddress

from concurrent.futures import ThreadPoolExecutor, as_completed


# ============================================================
# DJANGO SETUP
# ============================================================

# scanner.py is directly inside:
#
# NMS3/
# └── scanner.py
#
# Therefore this is the project root.

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

sys.path.append(BASE_DIR)

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "nms.settings"
)

import django

django.setup()


from django.utils import timezone
from dashboard.models import (
    Device,
    DeviceLog,
    DeviceStats,
    DeviceStatsHistory
)


# ============================================================
# SETTINGS
# ============================================================

MAX_WORKERS = 254


# ============================================================
# GET LOCAL IP
# ============================================================

def get_local_ip():

    """
    Get the IPv4 address of the computer running the scanner.
    """

    sock = None

    try:

        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        )

        # No actual connection/data transfer is required.
        # This helps Windows select the active network interface.

        sock.connect(
            ("8.8.8.8", 80)
        )

        local_ip = sock.getsockname()[0]

        return local_ip

    except Exception:

        try:

            hostname = socket.gethostname()

            local_ip = socket.gethostbyname(
                hostname
            )

            return local_ip

        except Exception:

            return None

    finally:

        if sock:

            sock.close()


# ============================================================
# DETECT NETWORK
# ============================================================

def get_network():

    """
    Automatically determine the current /24 network.

    Example:

        Local IP:
        192.168.1.25

        Detected network:
        192.168.1.0/24
    """

    local_ip = get_local_ip()

    if not local_ip:

        raise RuntimeError(
            "Unable to determine local IP address."
        )

    try:

        network = ipaddress.ip_network(
            f"{local_ip}/24",
            strict=False
        )

        return local_ip, network

    except Exception as e:

        raise RuntimeError(
            f"Unable to determine network: {e}"
        )


# ============================================================
# PING DEVICE
# ============================================================

def ping_device(ip):

    try:

        result = subprocess.run(

            [
                "ping",
                "-n",
                "1",
                "-w",
                "1000",
                ip
            ],

            capture_output=True,

            text=True,

            creationflags=subprocess.CREATE_NO_WINDOW

        )

        output = result.stdout.lower()

        # Device is unreachable

        if (

            "reply from" not in output

            or

            "destination host unreachable"
            in output

        ):

            return False, 0

        # Normal response:
        #
        # time=2ms
        # time<1ms

        match = re.search(

            r"time[=<]\s*(\d+)\s*ms",

            output

        )

        if match:

            latency = float(
                match.group(1)
            )

        elif "<1ms" in output:

            latency = 0.5

        else:

            latency = 0

        return True, latency

    except Exception as e:

        print(
            f"[PING ERROR] {ip}: {e}"
        )

        return False, 0


# ============================================================
# GET ARP TABLE
# ============================================================

def get_arp_table():

    arp_table = {}

    try:

        result = subprocess.run(

            [
                "arp",
                "-a"
            ],

            capture_output=True,

            text=True,

            creationflags=subprocess.CREATE_NO_WINDOW

        )

        for line in result.stdout.splitlines():

            match = re.search(

                r"(\d+\.\d+\.\d+\.\d+)\s+"
                r"([0-9a-fA-F-]{17})",

                line

            )

            if match:

                ip = match.group(1)

                mac = match.group(2)

                mac = mac.replace(
                    "-",
                    ":"
                ).lower()

                arp_table[ip] = mac

    except Exception as e:

        print(
            f"[ARP ERROR] {e}"
        )

    return arp_table


# ============================================================
# GET MAC ADDRESS
# ============================================================

def get_mac_address(
    ip,
    arp_table
):

    return arp_table.get(
        ip,
        None
    )


# ============================================================
# GET HOSTNAME
# ============================================================

def get_hostname(ip):

    try:

        result = subprocess.run(

            [
                "nslookup",
                ip
            ],

            capture_output=True,

            text=True,

            creationflags=subprocess.CREATE_NO_WINDOW

        )

        output = result.stdout

        for line in output.splitlines():

            if "name =" in line.lower():

                name = line.split(
                    "=",
                    1
                )[1].strip()

                if name:

                    return name.rstrip(".")

    except Exception:

        pass

    return None


# ============================================================
# DEVICE INFORMATION
# ============================================================

def get_device_information(
    ip,
    arp_table
):

    mac_address = get_mac_address(
        ip,
        arp_table
    )

    hostname = get_hostname(
        ip
    )

    return hostname, mac_address


# ============================================================
# UPDATE DEVICE
# ============================================================

def update_device(
    ip,
    hostname,
    mac_address
):

    now = timezone.now()

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

    # --------------------------------------------------------
    # NEW DEVICE
    # --------------------------------------------------------

    if created:

        DeviceLog.objects.create(

            device=device,

            status="Online",

            message="New device detected"

        )

        return device


    # --------------------------------------------------------
    # EXISTING DEVICE
    # --------------------------------------------------------

    was_offline = (
        device.status != "Online"
    )

    device.hostname = hostname

    if mac_address:

        device.mac_address = mac_address

    device.status = "Online"

    device.last_seen = now


    # --------------------------------------------------------
    # DEVICE CAME BACK ONLINE
    # --------------------------------------------------------

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


# ============================================================
# UPDATE DEVICE STATISTICS
# ============================================================

def update_device_stats(
    device,
    latency_ms
):

    now = timezone.now()

    stats, created = (
        DeviceStats.objects.get_or_create(
            device=device
        )
    )

    # --------------------------------------------------------
    # CURRENT STATISTICS
    # --------------------------------------------------------

    stats.packets_sent += 1

    stats.packets_received += 1

    stats.latency_ms = latency_ms

    stats.last_poll_time = now

    stats.save()


    # --------------------------------------------------------
    # HISTORICAL STATISTICS
    # --------------------------------------------------------
    #
    # The scanner sends one ping for every discovered device.
    #
    # Successful ping:
    #
    # Sent     = 1
    # Received = 1
    # Lost     = 0
    # Loss     = 0%
    #
    # This record is used by the historical graphs.

    packets_sent = 1

    packets_received = 1

    packets_lost = (
        packets_sent
        - packets_received
    )

    packet_loss = (
        (packets_lost / packets_sent) * 100
        if packets_sent > 0
        else 0
    )

    DeviceStatsHistory.objects.create(

        device=device,

        timestamp=now,

        latency_ms=latency_ms,

        packets_sent=packets_sent,

        packets_received=packets_received,

        packets_lost=packets_lost,

        packet_loss=packet_loss

    )


# ============================================================
# GENERATE IP ADDRESSES
# ============================================================

def generate_ips(network):

    """
    Generate all usable IP addresses
    inside the detected network.

    Example:

        192.168.1.0/24

    generates:

        192.168.1.1
        192.168.1.2
        ...
        192.168.1.254
    """

    return [

        str(ip)

        for ip in network.hosts()

    ]


# ============================================================
# CLEAR OLD DATABASE
# ============================================================

def clear_old_database():

    """
    Remove all devices from the previous scan.

    Because DeviceLog and DeviceStats use relationships
    with Device and have CASCADE deletion configured,
    deleting Device records also removes their related
    logs and statistics.
    """

    print()

    print(
        "[DATABASE] Clearing previous scan data..."
    )

    old_device_count = Device.objects.count()

    old_log_count = DeviceLog.objects.count()

    old_stats_count = DeviceStats.objects.count()

    print(
        f"[DATABASE] Old devices  : {old_device_count}"
    )

    print(
        f"[DATABASE] Old logs     : {old_log_count}"
    )

    print(
        f"[DATABASE] Old stats    : {old_stats_count}"
    )

    # Delete all devices.
    #
    # DeviceLog and DeviceStats are related to Device
    # using CASCADE, so their related records are removed.

    Device.objects.all().delete()

    print(
        "[DATABASE] Previous scan data deleted."
    )

    print()


# ============================================================
# SCAN NETWORK
# ============================================================

def scan_network():

    print()

    print(
        "========================================"
    )

    print(
        "      NETWORK DISCOVERY STARTED"
    )

    print(
        "========================================"
    )


    # --------------------------------------------------------
    # DETECT NETWORK
    # --------------------------------------------------------

    try:

        local_ip, network = get_network()

    except Exception as e:

        print(
            f"[NETWORK ERROR] {e}"
        )

        print(
            "[DATABASE] Existing database was NOT changed."
        )

        return


    print(
        f"Local IP : {local_ip}"
    )

    print(
        f"Network  : {network}"
    )

    print(
        "Method   : Ping + ARP"
    )

    print(
        "SNMP     : Disabled"
    )

    print()


    # --------------------------------------------------------
    # GENERATE IPs
    # --------------------------------------------------------

    ips = generate_ips(
        network
    )

    print(
        f"Scanning {len(ips)} IP addresses..."
    )

    print()


    online_devices = []


    # --------------------------------------------------------
    # PING
    # --------------------------------------------------------

    print(
        "[1/3] Pinging network..."
    )


    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        future_map = {

            executor.submit(
                ping_device,
                ip
            ): ip

            for ip in ips

        }


        for future in as_completed(
            future_map
        ):

            ip = future_map[future]


            try:

                is_online, latency = (
                    future.result()
                )


                if is_online:

                    online_devices.append(

                        (
                            ip,
                            latency
                        )

                    )


                    print(

                        f"[ONLINE] "
                        f"{ip} "
                        f"({latency} ms)"

                    )


            except Exception as e:

                print(

                    f"[ERROR] "
                    f"{ip}: {e}"

                )


    print()


    # --------------------------------------------------------
    # ARP
    # --------------------------------------------------------

    print(
        "[2/3] Reading ARP table..."
    )


    arp_table = get_arp_table()


    print(

        f"ARP entries found: "
        f"{len(arp_table)}"

    )

    print()


    # --------------------------------------------------------
    # DATABASE
    # --------------------------------------------------------

    print(
        "[3/3] Refreshing database..."
    )


    # IMPORTANT:
    #
    # We clear the database ONLY AFTER:
    #
    # 1. Network detection succeeded
    # 2. Ping scan completed
    # 3. ARP table was successfully read
    #
    # This prevents an accidental database wipe if
    # network detection fails.

    clear_old_database()


    # --------------------------------------------------------
    # INSERT CURRENT SCAN RESULTS
    # --------------------------------------------------------

    online_ips = set()


    for ip, latency in online_devices:

        online_ips.add(
            ip
        )


        hostname, mac_address = (
            get_device_information(
                ip,
                arp_table
            )
        )


        device = update_device(

            ip,

            hostname,

            mac_address

        )


        update_device_stats(

            device,

            latency

        )


    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print()

    print(
        "========================================"
    )

    print(
        "       NETWORK DISCOVERY COMPLETE"
    )

    print(
        "========================================"
    )

    print(
        f"Local IP        : {local_ip}"
    )

    print(
        f"Network         : {network}"
    )

    print(
        f"Online devices  : {len(online_ips)}"
    )

    print(
        f"Database devices: "
        f"{Device.objects.count()}"
    )

    print(
        "Scanner stopped."
    )

    print(
        "========================================"
    )

    print()


# ============================================================
# MANUAL EXECUTION ONLY
# ============================================================

if __name__ == "__main__":

    scan_network()