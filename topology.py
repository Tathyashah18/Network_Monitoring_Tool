import os
import sys
import re
import socket
import subprocess
import json
import urllib.parse

import django


# ============================================================
# DJANGO SETUP
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "nms.settings"
)

django.setup()

from dashboard.models import Device


# ============================================================
# OUTPUT FILE
# ============================================================

OUTPUT_FILE = os.path.join(
    BASE_DIR,
    "topology.html"
)


# ============================================================
# NETWORK INFORMATION
# ============================================================

def get_local_ip():
    """
    Get the local machine IP address.
    """

    try:

        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        )

        sock.connect(
            ("8.8.8.8", 80)
        )

        local_ip = sock.getsockname()[0]

        sock.close()

        return local_ip

    except Exception:

        try:

            return socket.gethostbyname(
                socket.gethostname()
            )

        except Exception:

            return "127.0.0.1"


def get_default_gateway():
    """
    Get the default gateway using Windows ipconfig.
    """

    try:

        result = subprocess.check_output(
            ["ipconfig"],
            encoding="utf-8",
            errors="ignore"
        )

        match = re.search(
            r"Default Gateway[ .:]+(\d+\.\d+\.\d+\.\d+)",
            result,
            re.IGNORECASE
        )

        if match:
            return match.group(1)

        return None

    except Exception:

        return None


def get_arp_table():
    """
    Get ARP table from Windows.
    """

    arp_table = {}

    try:

        result = subprocess.check_output(
            ["arp", "-a"],
            encoding="utf-8",
            errors="ignore"
        )

        for line in result.splitlines():

            match = re.search(
                r"(\d+\.\d+\.\d+\.\d+)\s+"
                r"([0-9a-fA-F:-]{17})\s+"
                r"(\w+)",
                line
            )

            if match:

                ip = match.group(1)
                mac = match.group(2)

                arp_table[ip] = mac

    except Exception:

        pass

    return arp_table


# ============================================================
# PING
# ============================================================

def ping_device(ip):
    """
    Ping a device once.
    """

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
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        return result.returncode == 0

    except Exception:

        return False


# ============================================================
# HOSTNAME
# ============================================================

def get_hostname(ip):
    """
    Resolve hostname from IP.
    """

    try:

        hostname = socket.gethostbyaddr(ip)[0]

        if hostname:
            return hostname

    except Exception:

        pass

    return ""


# ============================================================
# DEVICE TYPE
# ============================================================

def determine_device_type(
    ip,
    hostname,
    gateway,
    mac=""
):
    """
    Determine a logical device type.
    """

    ip = str(ip).lower()

    hostname = str(
        hostname or ""
    ).lower()

    gateway = str(
        gateway or ""
    ).lower()

    mac = str(
        mac or ""
    ).lower()

    # --------------------------------------------------------
    # GATEWAY
    # --------------------------------------------------------

    if gateway and ip == gateway:

        return "Router"

    # --------------------------------------------------------
    # ROUTER
    # --------------------------------------------------------

    router_keywords = [
        "router",
        "gateway",
        "mikrotik",
        "cisco",
        "tp-link",
        "tplink",
        "netgear",
        "asus",
        "dlink"
    ]

    for keyword in router_keywords:

        if keyword in hostname:

            return "Router"

    # --------------------------------------------------------
    # SWITCH
    # --------------------------------------------------------

    switch_keywords = [
        "switch",
        "managed-switch"
    ]

    for keyword in switch_keywords:

        if keyword in hostname:

            return "Switch"

    # --------------------------------------------------------
    # ACCESS POINT
    # --------------------------------------------------------

    ap_keywords = [
        "access-point",
        "accesspoint",
        "wifi",
        "wireless",
        "wlan",
        "access point"
    ]

    for keyword in ap_keywords:

        if keyword in hostname:

            return "Access Point"

    # --------------------------------------------------------
    # SERVER
    # --------------------------------------------------------

    server_keywords = [
        "server",
        "srv",
        "nas",
        "database",
        "db-server",
        "web-server",
        "mail-server",
        "file-server"
    ]

    for keyword in server_keywords:

        if keyword in hostname:

            return "Server"

    # --------------------------------------------------------
    # DEFAULT
    # --------------------------------------------------------

    return "Device"


# ============================================================
# BUILD TOPOLOGY
# ============================================================

def build_topology():
    """
    Build the logical network topology.

    Current hierarchy:

        Internet
            |
         Gateway
            |
        Devices

    monitor.py remains responsible for continuously
    updating Device.status.
    """

    local_ip = get_local_ip()

    gateway = get_default_gateway()

    arp_table = get_arp_table()

    nodes = []

    edges = []

    # --------------------------------------------------------
    # INTERNET
    # --------------------------------------------------------

    nodes.append(
        {
            "id": "internet",
            "label": "Internet",
            "type": "Internet",
            "level": 0,
            "ip": "",
            "hostname": "Internet",
            "status": "Online",
            "mac": ""
        }
    )

    # --------------------------------------------------------
    # GATEWAY
    # --------------------------------------------------------

    if gateway:

        gateway_mac = arp_table.get(
            gateway,
            ""
        )

        gateway_hostname = get_hostname(
            gateway
        )

        nodes.append(
            {
                "id": gateway,
                "label": "Gateway",
                "type": "Router",
                "level": 1,
                "ip": gateway,
                "hostname": gateway_hostname,
                "status": "Online",
                "mac": gateway_mac
            }
        )

        edges.append(
            {
                "from": "internet",
                "to": gateway
            }
        )

    # --------------------------------------------------------
    # DATABASE DEVICES
    # --------------------------------------------------------

    devices = Device.objects.all().order_by(
        "ip_address"
    )

    for device in devices:

        ip = device.ip_address

        # Do not add gateway twice
        if gateway and ip == gateway:
            continue

        hostname = (
            device.hostname
            or ""
        )

        if not hostname:

            hostname = get_hostname(
                ip
            )

        mac = (
            device.mac_address
            or arp_table.get(ip, "")
            or ""
        )

        device_type = determine_device_type(
            ip=ip,
            hostname=hostname,
            gateway=gateway,
            mac=mac
        )

        status = (
            device.status
            or "Offline"
        )

        # ----------------------------------------------------
        # LABEL
        # ----------------------------------------------------

        if device_type == "Router":

            label = "Router"

        elif device_type == "Switch":

            label = "Switch"

        elif device_type == "Access Point":

            label = "Access Point"

        elif device_type == "Server":

            label = (
                hostname
                if hostname
                else "Server"
            )

        else:

            label = (
                hostname
                if hostname
                else ip
            )

        nodes.append(
            {
                "id": ip,
                "label": label,
                "type": device_type,
                "level": 2,
                "ip": ip,
                "hostname": hostname,
                "status": status,
                "mac": mac
            }
        )

        # ----------------------------------------------------
        # CONNECT DEVICE TO GATEWAY
        # ----------------------------------------------------

        if gateway:

            parent_node = gateway

        else:

            parent_node = "internet"

        edges.append(
            {
                "from": parent_node,
                "to": ip
            }
        )

    return (
        local_ip,
        gateway,
        nodes,
        edges
    )


# ============================================================
# ICON GENERATOR
# ============================================================

def create_icon(
    device_type,
    color,
    offline=False
):
    """
    Generate an inline SVG icon.
    """

    stroke_width = 2

    if offline:

        opacity = "0.95"

    else:

        opacity = "1"

    # --------------------------------------------------------
    # INTERNET
    # --------------------------------------------------------

    if device_type == "Internet":

        svg = f"""
        <svg xmlns="http://www.w3.org/2000/svg"
             width="80"
             height="80"
             viewBox="0 0 80 80">

            <circle
                cx="40"
                cy="40"
                r="31"
                fill="white"
                stroke="{color}"
                stroke-width="4"
                opacity="{opacity}"
            />

            <circle
                cx="40"
                cy="40"
                r="24"
                fill="none"
                stroke="{color}"
                stroke-width="{stroke_width}"
            />

            <path
                d="M16 40h48"
                stroke="{color}"
                stroke-width="{stroke_width}"
                fill="none"
            />

            <path
                d="M40 16c8 7 12 15 12 24s-4 17-12 24"
                stroke="{color}"
                stroke-width="{stroke_width}"
                fill="none"
            />

            <path
                d="M40 16c-8 7-12 15-12 24s4 17 12 24"
                stroke="{color}"
                stroke-width="{stroke_width}"
                fill="none"
            />

        </svg>
        """

    # --------------------------------------------------------
    # ROUTER
    # --------------------------------------------------------

    elif device_type == "Router":

        svg = f"""
        <svg xmlns="http://www.w3.org/2000/svg"
             width="80"
             height="80"
             viewBox="0 0 80 80">

            <rect
                x="14"
                y="25"
                width="52"
                height="30"
                rx="6"
                fill="white"
                stroke="{color}"
                stroke-width="4"
                opacity="{opacity}"
            />

            <line
                x1="22"
                y1="34"
                x2="58"
                y2="34"
                stroke="{color}"
                stroke-width="3"
            />

            <circle
                cx="25"
                cy="46"
                r="3"
                fill="{color}"
            />

            <circle
                cx="40"
                cy="46"
                r="3"
                fill="{color}"
            />

            <circle
                cx="55"
                cy="46"
                r="3"
                fill="{color}"
            />

            <line
                x1="40"
                y1="25"
                x2="40"
                y2="15"
                stroke="{color}"
                stroke-width="3"
            />

            <line
                x1="30"
                y1="19"
                x2="40"
                y2="15"
                stroke="{color}"
                stroke-width="3"
            />

            <line
                x1="50"
                y1="19"
                x2="40"
                y2="15"
                stroke="{color}"
                stroke-width="3"
            />

        </svg>
        """

    # --------------------------------------------------------
    # SWITCH
    # --------------------------------------------------------

    elif device_type == "Switch":

        svg = f"""
        <svg xmlns="http://www.w3.org/2000/svg"
             width="80"
             height="80"
             viewBox="0 0 80 80">

            <rect
                x="10"
                y="25"
                width="60"
                height="30"
                rx="5"
                fill="white"
                stroke="{color}"
                stroke-width="4"
                opacity="{opacity}"
            />

            <circle
                cx="22"
                cy="40"
                r="3"
                fill="{color}"
            />

            <circle
                cx="34"
                cy="40"
                r="3"
                fill="{color}"
            />

            <circle
                cx="46"
                cy="40"
                r="3"
                fill="{color}"
            />

            <circle
                cx="58"
                cy="40"
                r="3"
                fill="{color}"
            />

        </svg>
        """

    # --------------------------------------------------------
    # ACCESS POINT
    # --------------------------------------------------------

    elif device_type == "Access Point":

        svg = f"""
        <svg xmlns="http://www.w3.org/2000/svg"
             width="80"
             height="80"
             viewBox="0 0 80 80">

            <circle
                cx="40"
                cy="47"
                r="8"
                fill="white"
                stroke="{color}"
                stroke-width="4"
                opacity="{opacity}"
            />

            <path
                d="M24 35c9-9 23-9 32 0"
                stroke="{color}"
                stroke-width="4"
                fill="none"
                stroke-linecap="round"
            />

            <path
                d="M16 27c13-13 35-13 48 0"
                stroke="{color}"
                stroke-width="4"
                fill="none"
                stroke-linecap="round"
            />

            <line
                x1="40"
                y1="55"
                x2="40"
                y2="66"
                stroke="{color}"
                stroke-width="4"
            />

        </svg>
        """

    # --------------------------------------------------------
    # SERVER
    # --------------------------------------------------------

    elif device_type == "Server":

        svg = f"""
        <svg xmlns="http://www.w3.org/2000/svg"
             width="80"
             height="80"
             viewBox="0 0 80 80">

            <rect
                x="20"
                y="10"
                width="40"
                height="60"
                rx="5"
                fill="white"
                stroke="{color}"
                stroke-width="4"
                opacity="{opacity}"
            />

            <rect
                x="27"
                y="18"
                width="26"
                height="12"
                rx="2"
                fill="{color}"
                opacity="0.15"
            />

            <rect
                x="27"
                y="35"
                width="26"
                height="12"
                rx="2"
                fill="{color}"
                opacity="0.15"
            />

            <rect
                x="27"
                y="52"
                width="26"
                height="10"
                rx="2"
                fill="{color}"
                opacity="0.15"
            />

            <circle
                cx="32"
                cy="24"
                r="2"
                fill="{color}"
            />

            <circle
                cx="32"
                cy="41"
                r="2"
                fill="{color}"
            />

            <circle
                cx="32"
                cy="57"
                r="2"
                fill="{color}"
            />

        </svg>
        """

    # --------------------------------------------------------
    # NORMAL DEVICE
    # --------------------------------------------------------

    else:

        svg = f"""
        <svg xmlns="http://www.w3.org/2000/svg"
             width="80"
             height="80"
             viewBox="0 0 80 80">

            <rect
                x="12"
                y="13"
                width="56"
                height="40"
                rx="4"
                fill="white"
                stroke="{color}"
                stroke-width="4"
                opacity="{opacity}"
            />

            <rect
                x="18"
                y="19"
                width="44"
                height="28"
                rx="2"
                fill="{color}"
                opacity="0.12"
            />

            <line
                x1="28"
                y1="62"
                x2="52"
                y2="62"
                stroke="{color}"
                stroke-width="4"
                stroke-linecap="round"
            />

            <line
                x1="40"
                y1="53"
                x2="40"
                y2="62"
                stroke="{color}"
                stroke-width="4"
            />

        </svg>
        """

    encoded_svg = urllib.parse.quote(
        svg
    )

    return (
        "data:image/svg+xml;charset=utf-8,"
        + encoded_svg
    )


# ============================================================
# HTML GENERATOR
# ============================================================

def generate_html(
    local_ip=None,
    gateway=None,
    nodes=None,
    edges=None
):
    """
    Generate topology.html.

    Compatible with existing views.py:

        topology.generate_html()
    """

    if nodes is None or edges is None:

        (
            local_ip,
            gateway,
            nodes,
            edges
        ) = build_topology()

    visual_nodes = []

    # --------------------------------------------------------
    # CREATE VISUAL NODES
    # --------------------------------------------------------

    for node in nodes:

        device_type = node.get(
            "type",
            "Device"
        )

        status = str(
            node.get(
                "status",
                "Online"
            )
        ).lower()

        is_offline = (
            status == "offline"
        )

        # ----------------------------------------------------
        # BASE COLOR
        # ----------------------------------------------------

        if device_type == "Internet":

            base_color = "#2563eb"

        elif device_type == "Router":

            base_color = "#dc2626"

        elif device_type == "Switch":

            base_color = "#7c3aed"

        elif device_type == "Access Point":

            base_color = "#059669"

        elif device_type == "Server":

            base_color = "#0891b2"

        else:

            base_color = "#2563eb"

        # ----------------------------------------------------
        # ONLINE ICON
        # ----------------------------------------------------

        online_icon = create_icon(
            device_type,
            base_color,
            offline=False
        )

        # ----------------------------------------------------
        # OFFLINE ICON
        # ----------------------------------------------------

        offline_icon = create_icon(
            device_type,
            "#dc2626",
            offline=True
        )

        # ----------------------------------------------------
        # INITIAL VISUAL STATE
        # ----------------------------------------------------

        if (
            is_offline
            and
            device_type not in [
                "Internet",
                "Router",
                "Switch",
                "Access Point"
            ]
        ):

            initial_icon = offline_icon

            border_width = 4

            shadow = {
                "enabled": True,
                "color": "rgba(220,38,38,0.55)",
                "size": 18,
                "x": 0,
                "y": 0
            }

        else:

            initial_icon = online_icon

            border_width = 2

            shadow = {
                "enabled": False
            }

        # ----------------------------------------------------
        # TOOLTIP
        # ----------------------------------------------------

        if device_type == "Internet":

            title = "Internet"

        else:

            hostname_display = node.get(
                "hostname",
                ""
            )

            if hostname_display:

                title = hostname_display

            else:

                title = node.get(
                    "ip",
                    ""
                )

        # ----------------------------------------------------
        # VISUAL NODE
        # ----------------------------------------------------

        visual_node = {

            "id": node["id"],

            "label": node.get(
                "label",
                node["id"]
            ),

            "shape": "image",

            "image": initial_icon,

            "brokenImage": online_icon,

            "onlineImage": online_icon,

            "offlineImage": offline_icon,

            "deviceType": device_type,

            "deviceStatus": status,

            "size": 30,

            "level": node.get(
                "level",
                2
            ),

            "title": title,

            "font": {
                "size": 14,
                "face": "Arial",
                "color": "#111827"
            },

            "borderWidth": border_width,

            "shadow": shadow
        }

        visual_nodes.append(
            visual_node
        )

    # --------------------------------------------------------
    # CREATE EDGE INITIAL STATUS
    # --------------------------------------------------------

    node_status_map = {}

    for node in visual_nodes:

        node_status_map[
            str(node["id"])
        ] = str(
            node.get(
                "deviceStatus",
                "online"
            )
        ).lower()

    visual_edges = []

    for index, edge in enumerate(edges):

        edge_from = str(
            edge.get("from", "")
        )

        edge_to = str(
            edge.get("to", "")
        )

        from_status = node_status_map.get(
            edge_from,
            "online"
        )

        to_status = node_status_map.get(
            edge_to,
            "online"
        )

        if (
            from_status == "offline"
            or
            to_status == "offline"
        ):

            edge_color = "#dc2626"

            edge_status = "offline"

            edge_dashes = [8, 8]

            edge_width = 2

        else:

            edge_color = "#64748b"

            edge_status = "online"

            edge_dashes = False

            edge_width = 2

        visual_edges.append(
            {
                "id": "edge_" + str(index),
                "from": edge.get("from"),
                "to": edge.get("to"),
                "edgeStatus": edge_status,
                "color": {
                    "color": edge_color,
                    "highlight": "#2563eb",
                    "hover": "#2563eb"
                },
                "width": edge_width,
                "dashes": edge_dashes,
                "arrows": {
                    "to": {
                        "enabled": True,
                        "scaleFactor": 0.8
                    }
                },
                "smooth": {
                    "type": "cubicBezier",
                    "forceDirection": "vertical",
                    "roundness": 0.4
                }
            }
        )

    # --------------------------------------------------------
    # JSON DATA
    # --------------------------------------------------------

    nodes_json = json.dumps(
        visual_nodes
    )

    edges_json = json.dumps(
        visual_edges
    )

    # ========================================================
    # HTML
    # ========================================================

    html = f"""<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>Network Topology</title>

<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>

<style>

* {{
    box-sizing: border-box;
}}

html,
body {{
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    font-family: Arial, Helvetica, sans-serif;
    background: #f8fafc;
}}

body {{
    overflow: hidden;
}}


/* =========================================================
   HEADER
   ========================================================= */

.header {{
    height: 82px;
    width: 100%;
    background: #ffffff;
    border-bottom: 1px solid #d1d5db;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 20px;
    position: relative;
    z-index: 1000;
}}

.header-left {{
    display: flex;
    align-items: center;
    gap: 15px;
}}

.back-button {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    text-decoration: none;
    background: #2563eb;
    color: white;
    padding: 10px 16px;
    border-radius: 7px;
    font-size: 14px;
    font-weight: 600;
    transition: 0.2s;
}}

.back-button:hover {{
    background: #1d4ed8;
}}

.title-section {{
    display: flex;
    flex-direction: column;
    gap: 3px;
}}

.title {{
    font-size: 22px;
    font-weight: 700;
    color: #111827;
}}

.subtitle {{
    font-size: 12px;
    color: #6b7280;
}}

.header-right {{
    display: flex;
    gap: 8px;
}}

.header-button {{
    border: none;
    padding: 9px 14px;
    border-radius: 7px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    background: #eef2ff;
    color: #3730a3;
}}

.header-button:hover {{
    background: #e0e7ff;
}}


/* =========================================================
   NETWORK
   ========================================================= */

#network {{
    width: 100%;
    height: calc(100vh - 82px);
    background: #f8fafc;
}}


/* =========================================================
   FILTER PANEL
   ========================================================= */

.filter-panel {{
    position: absolute;
    top: 102px;
    left: 20px;
    z-index: 1000;
    width: 210px;
    padding: 14px;
    background: rgba(255, 255, 255, 0.97);
    border: 1px solid #d1d5db;
    border-radius: 10px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
}}

.filter-title {{
    font-size: 13px;
    font-weight: 700;
    color: #111827;
    margin-bottom: 10px;
}}

.filter-select {{
    width: 100%;
    padding: 9px 10px;
    border: 1px solid #d1d5db;
    border-radius: 7px;
    background: #ffffff;
    color: #111827;
    font-size: 13px;
    cursor: pointer;
    outline: none;
}}

.filter-select:focus {{
    border-color: #2563eb;
    box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.12);
}}

.filter-count {{
    margin-top: 9px;
    font-size: 11px;
    color: #6b7280;
}}


/* =========================================================
   LEGEND
   ========================================================= */

.legend {{
    position: absolute;
    top: 102px;
    right: 20px;
    z-index: 1000;
    min-width: 190px;
    padding: 13px 15px;
    background: rgba(255, 255, 255, 0.97);
    border: 1px solid #d1d5db;
    border-radius: 10px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
    display: flex;
    flex-direction: column;
    gap: 8px;
}}

.legend-title {{
    font-size: 13px;
    font-weight: 700;
    color: #111827;
    margin-bottom: 3px;
}}

.legend-item {{
    display: flex;
    align-items: center;
    gap: 9px;
    font-size: 12px;
    color: #374151;
}}

.legend-icon {{
    width: 15px;
    height: 15px;
    border-radius: 50%;
    flex-shrink: 0;
}}

.legend-internet {{
    background: #2563eb;
}}

.legend-router {{
    background: #dc2626;
}}

.legend-switch {{
    background: #7c3aed;
}}

.legend-ap {{
    background: #059669;
}}

.legend-online {{
    background: #2563eb;
}}

.legend-offline {{
    background: #dc2626;
    box-shadow: 0 0 9px rgba(220, 38, 38, 0.75);
}}


/* =========================================================
   CHILD DEVICE PANEL
   ========================================================= */

.child-panel {{
    position: absolute;
    top: 102px;
    right: 20px;
    width: 300px;
    max-height: calc(100vh - 125px);
    overflow-y: auto;
    z-index: 1100;
    display: none;
    background: rgba(255, 255, 255, 0.98);
    border: 1px solid #d1d5db;
    border-radius: 10px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16);
}}

.child-panel-header {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
    padding: 15px;
    border-bottom: 1px solid #e5e7eb;
}}

.child-panel-title {{
    font-size: 15px;
    font-weight: 700;
    color: #111827;
}}

.child-panel-subtitle {{
    margin-top: 3px;
    font-size: 11px;
    color: #6b7280;
}}

.child-close {{
    border: none;
    background: #f3f4f6;
    color: #374151;
    width: 28px;
    height: 28px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 16px;
    line-height: 28px;
}}

.child-close:hover {{
    background: #e5e7eb;
}}

.child-summary {{
    padding: 10px 15px;
    font-size: 12px;
    color: #4b5563;
    background: #f8fafc;
    border-bottom: 1px solid #e5e7eb;
}}

.child-list {{
    padding: 10px;
}}

.child-item {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 10px;
    margin-bottom: 7px;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: #ffffff;
    cursor: pointer;
    transition: 0.15s;
}}

.child-item:hover {{
    border-color: #93c5fd;
    background: #eff6ff;
}}

.child-info {{
    min-width: 0;
}}

.child-name {{
    font-size: 12px;
    font-weight: 700;
    color: #111827;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}}

.child-ip {{
    margin-top: 3px;
    font-size: 10px;
    color: #6b7280;
}}

.child-status {{
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 10px;
    font-weight: 600;
}}

.child-status-dot {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
}}

.child-status-online {{
    background: #16a34a;
}}

.child-status-offline {{
    background: #dc2626;
    box-shadow: 0 0 7px rgba(220, 38, 38, 0.55);
}}

.child-empty {{
    padding: 18px 12px;
    text-align: center;
    font-size: 12px;
    line-height: 1.5;
    color: #6b7280;
}}


/* =========================================================
   NODE HIGHLIGHT
   ========================================================= */

.node-highlight {{
    filter: drop-shadow(
        0 0 10px
        rgba(37, 99, 235, 0.8)
    );
}}


/* =========================================================
   EDGE ANIMATION
   ========================================================= */

@keyframes edgePulse {{
    0% {{
        opacity: 0.35;
    }}

    50% {{
        opacity: 1;
    }}

    100% {{
        opacity: 0.35;
    }}
}}


/* =========================================================
   RESPONSIVE
   ========================================================= */

@media (max-width: 700px) {{

    .header {{
        padding: 0 10px;
    }}

    .title {{
        font-size: 17px;
    }}

    .subtitle {{
        display: none;
    }}

    .back-button {{
        padding: 8px 10px;
        font-size: 12px;
    }}

    .header-button {{
        padding: 8px 10px;
        font-size: 12px;
    }}

    .filter-panel {{
        left: 10px;
        top: 95px;
        width: 175px;
    }}

    .legend {{
        top: 95px;
        right: 10px;
        min-width: 165px;
    }}

    .child-panel {{
        top: 95px;
        right: 10px;
        left: 10px;
        width: auto;
        max-height: 45vh;
    }}

}}

</style>

</head>

<body>


<!-- =======================================================
     HEADER
     ======================================================= -->

<div class="header">

    <div class="header-left">

        <a
            href="/"
            class="back-button"
        >
            &#8592; Back to Dashboard
        </a>

        <div class="title-section">

            <div class="title">
                Network Topology
            </div>

            <div class="subtitle">
                Live network device topology
            </div>

        </div>

    </div>

    <div class="header-right">

        <button
            class="header-button"
            onclick="fitNetwork()"
        >
            Fit
        </button>

        <button
            class="header-button"
            onclick="location.reload()"
        >
            Refresh
        </button>

    </div>

</div>


<!-- =======================================================
     FILTER PANEL
     ======================================================= -->

<div class="filter-panel">

    <div class="filter-title">
        Filter Nodes
    </div>

    <select
        id="nodeFilter"
        class="filter-select"
        onchange="applyNodeFilter()"
    >

        <option value="all">
            All Devices
        </option>

        <option value="online">
            Online
        </option>

        <option value="offline">
            Offline
        </option>

        <option value="Router">
            Routers
        </option>

        <option value="Switch">
            Switches
        </option>

        <option value="Access Point">
            Access Points
        </option>

        <option value="Server">
            Servers
        </option>

        <option value="Device">
            Devices
        </option>

    </select>

    <div
        id="filterCount"
        class="filter-count"
    >
        Showing all nodes
    </div>

</div>


<!-- =======================================================
     LEGEND
     ======================================================= -->

<div class="legend">

    <div class="legend-title">
        Legend
    </div>

    <div class="legend-item">

        <span
            class="legend-icon legend-internet"
        ></span>

        Internet

    </div>

    <div class="legend-item">

        <span
            class="legend-icon legend-router"
        ></span>

        Router / Gateway

    </div>

    <div class="legend-item">

        <span
            class="legend-icon legend-switch"
        ></span>

        Switch

    </div>

    <div class="legend-item">

        <span
            class="legend-icon legend-ap"
        ></span>

        Access Point

    </div>

    <div class="legend-item">

        <span
            class="legend-icon legend-online"
        ></span>

        Online Device

    </div>

    <div class="legend-item">

        <span
            class="legend-icon legend-offline"
        ></span>

        Offline Device

    </div>

</div>


<!-- =======================================================
     CHILD DEVICE PANEL
     ======================================================= -->

<div
    id="childPanel"
    class="child-panel"
>

    <div class="child-panel-header">

        <div>

            <div
                id="childPanelTitle"
                class="child-panel-title"
            >
                Connected Devices
            </div>

            <div
                id="childPanelSubtitle"
                class="child-panel-subtitle"
            >
                Direct children
            </div>

        </div>

        <button
            class="child-close"
            onclick="closeChildPanel()"
            title="Close"
        >
            ×
        </button>

    </div>

    <div
        id="childSummary"
        class="child-summary"
    >
        Connected devices: 0
    </div>

    <div
        id="childList"
        class="child-list"
    ></div>

</div>


<!-- =======================================================
     NETWORK
     ======================================================= -->

<div id="network"></div>


<script>


/* =========================================================
   INITIAL DATA
   ========================================================= */

const initialNodes = {nodes_json};

const initialEdges = {edges_json};


/* =========================================================
   DATASETS
   ========================================================= */

const nodes = new vis.DataSet(
    initialNodes
);

const edges = new vis.DataSet(
    initialEdges
);


/* =========================================================
   ORIGINAL NODE DATA
   ========================================================= */

const allNodeData = initialNodes.map(
    function(node) {{
        return {{
            ...node
        }};
    }}
);


/* =========================================================
   ORIGINAL EDGE DATA
   ========================================================= */

const allEdgeData = initialEdges.map(
    function(edge) {{
        return {{
            ...edge
        }};
    }}
);


/* =========================================================
   CURRENT CHILD PARENT
   ========================================================= */

let selectedParentId = null;


/* =========================================================
   NETWORK OPTIONS
   ========================================================= */

const options = {{

    layout: {{

        hierarchical: {{

            enabled: true,

            direction: "UD",

            sortMethod: "directed",

            levelSeparation: 150,

            nodeSpacing: 180,

            treeSpacing: 250,

            blockShifting: true,

            edgeMinimization: true,

            parentCentralization: true

        }}

    }},

    physics: {{

        enabled: false

    }},

    interaction: {{

        hover: true,

        navigationButtons: true,

        keyboard: true,

        zoomView: true,

        dragView: true

    }},

    nodes: {{

        shape: "image",

        size: 30,

        borderWidth: 2,

        margin: 10,

        font: {{

            size: 14,

            face: "Arial",

            color: "#111827"

        }}

    }},

    edges: {{

        color: {{

            color: "#64748b",

            highlight: "#2563eb",

            hover: "#2563eb"

        }},

        width: 2,

        arrows: {{

            to: {{

                enabled: true,

                scaleFactor: 0.8

            }}

        }},

        smooth: {{

            type: "cubicBezier",

            forceDirection: "vertical",

            roundness: 0.4

        }}

    }}

}};


/* =========================================================
   CREATE NETWORK
   ========================================================= */

const container = document.getElementById(
    "network"
);

const network = new vis.Network(
    container,
    {{
        nodes: nodes,
        edges: edges
    }},
    options
);


/* =========================================================
   FIT NETWORK
   ========================================================= */

function fitNetwork() {{

    network.fit({{
        animation: {{
            duration: 500,
            easingFunction: "easeInOutQuad"
        }}
    }});

}}


/* =========================================================
   GET NODE VISUAL STATE
   ========================================================= */

function getNodeVisualState(node) {{

    const deviceType =
        node.deviceType || "Device";

    const status =
        String(
            node.deviceStatus || "online"
        ).toLowerCase();

    const isOffline =
        status === "offline";


    if (
        isOffline &&
        deviceType !== "Internet" &&
        deviceType !== "Router" &&
        deviceType !== "Switch" &&
        deviceType !== "Access Point"
    ) {{

        return {{

            image: node.offlineImage,

            borderWidth: 4,

            shadow: {{

                enabled: true,

                color:
                    "rgba(220,38,38,0.55)",

                size: 18,

                x: 0,

                y: 0

            }}

        }};

    }}


    return {{

        image: node.onlineImage,

        borderWidth: 2,

        shadow: {{

            enabled: false

        }}

    }};

}}


/* =========================================================
   GET EDGE VISUAL STATE
   ========================================================= */

function getEdgeVisualState(edge) {{

    const fromNode =
        allNodeData.find(
            function(node) {{
                return String(node.id) ===
                    String(edge.from);
            }}
        );

    const toNode =
        allNodeData.find(
            function(node) {{
                return String(node.id) ===
                    String(edge.to);
            }}
        );


    const fromStatus =
        String(
            fromNode
                ? fromNode.deviceStatus
                : "online"
        ).toLowerCase();


    const toStatus =
        String(
            toNode
                ? toNode.deviceStatus
                : "online"
        ).toLowerCase();


    const fromType =
        fromNode
            ? fromNode.deviceType
            : "Device";


    const toType =
        toNode
            ? toNode.deviceType
            : "Device";


    const infrastructureOffline =
        (
            (
                fromStatus === "offline"
                &&
                fromType !== "Internet"
            )
            ||
            (
                toStatus === "offline"
                &&
                toType !== "Internet"
            )
        );


    if (infrastructureOffline) {{

        return {{

            edgeStatus: "offline",

            color: {{

                color: "#dc2626",

                highlight: "#b91c1c",

                hover: "#b91c1c"

            }},

            width: 3,

            dashes: [8, 8]

        }};

    }}


    return {{

        edgeStatus: "online",

        color: {{

            color: "#64748b",

            highlight: "#2563eb",

            hover: "#2563eb"

        }},

        width: 2,

        dashes: false

    }};

}}


/* =========================================================
   APPLY EDGE STATUS
   ========================================================= */

function updateEdgeStatus() {{

    const updatedEdges = [];


    allEdgeData.forEach(
        function(edge) {{

            const visualState =
                getEdgeVisualState(edge);


            updatedEdges.push({{

                ...edge,

                ...visualState,

                arrows: {{

                    to: {{

                        enabled: true,

                        scaleFactor: 0.8

                    }}

                }},

                smooth: {{

                    type: "cubicBezier",

                    forceDirection: "vertical",

                    roundness: 0.4

                }}

            }});

        }}
    );


    const visibleIds =
        new Set(
            nodes.getIds().map(
                function(id) {{
                    return String(id);
                }}
            )
        );


    const visibleEdges =
        updatedEdges.filter(
            function(edge) {{

                return (
                    visibleIds.has(
                        String(edge.from)
                    )
                    &&
                    visibleIds.has(
                        String(edge.to)
                    )
                );

            }}
        );


    edges.clear();

    edges.add(
        visibleEdges
    );


    animateEdges();

}}


/* =========================================================
   ANIMATE ONLINE EDGES
   ========================================================= */

function animateEdges() {{

    const edgeElements =
        document.querySelectorAll(
            "#network canvas"
        );


    /*
     * vis-network renders edges on canvas.
     * Therefore CSS animation cannot directly
     * animate individual edges.
     *
     * We create a subtle visual pulse by
     * periodically increasing/decreasing the
     * width of online edges.
     */

    const currentEdges =
        edges.get();


    const pulse =
        (Date.now() % 1600) / 1600;


    const factor =
        2 +
        (
            Math.sin(
                pulse * Math.PI * 2
            ) * 0.5
        );


    currentEdges.forEach(
        function(edge) {{

            if (
                edge.edgeStatus === "online"
            ) {{

                edges.update({{

                    id: edge.id,

                    width: factor

                }});

            }}

        }}
    );

}}


/* =========================================================
   EDGE ANIMATION LOOP
   ========================================================= */

setInterval(
    animateEdges,
    400
);


/* =========================================================
   APPLY NODE FILTER
   ========================================================= */

function applyNodeFilter() {{

    const filter =
        document.getElementById(
            "nodeFilter"
        ).value;

    let filteredNodes = [];


    allNodeData.forEach(
        function(node) {{

            let visible = false;


            if (filter === "all") {{

                visible = true;

            }}


            else if (filter === "online") {{

                if (
                    node.deviceType !== "Internet" &&
                    node.deviceType !== "Router" &&
                    node.deviceType !== "Switch" &&
                    node.deviceType !== "Access Point"
                ) {{

                    visible =
                        String(
                            node.deviceStatus || ""
                        ).toLowerCase() !== "offline";

                }}

            }}


            else if (filter === "offline") {{

                if (
                    node.deviceType !== "Internet" &&
                    node.deviceType !== "Router" &&
                    node.deviceType !== "Switch" &&
                    node.deviceType !== "Access Point"
                ) {{

                    visible =
                        String(
                            node.deviceStatus || ""
                        ).toLowerCase() === "offline";

                }}

            }}


            else {{

                visible =
                    node.deviceType === filter;

            }}


            if (visible) {{

                const visualState =
                    getNodeVisualState(node);


                filteredNodes.push({{

                    ...node,

                    ...visualState

                }});

            }}

        }}
    );


    nodes.clear();

    nodes.add(
        filteredNodes
    );


    const visibleIds =
        new Set(
            filteredNodes.map(
                function(node) {{
                    return String(node.id);
                }}
            )
        );


    const filteredEdges =
        allEdgeData
            .map(
                function(edge) {{

                    return {{

                        ...edge,

                        ...getEdgeVisualState(edge)

                    }};

                }}
            )
            .filter(
                function(edge) {{

                    return (
                        visibleIds.has(
                            String(edge.from)
                        )
                        &&
                        visibleIds.has(
                            String(edge.to)
                        )
                    );

                }}
            );


    edges.clear();

    edges.add(
        filteredEdges
    );


    const countElement =
        document.getElementById(
            "filterCount"
        );


    if (filter === "all") {{

        countElement.textContent =
            "Showing all nodes";

    }}
    else {{

        countElement.textContent =
            "Showing " +
            filteredNodes.length +
            " node(s)";

    }}


    /*
     * Reapply selected parent highlighting
     * after filtering.
     */

    if (selectedParentId) {{

        showChildrenForParent(
            selectedParentId,
            false
        );

    }}


    setTimeout(
        fitNetwork,
        100
    );

}}


/* =========================================================
   GET DIRECT CHILDREN
   ========================================================= */

function getChildren(parentId) {{

    const childIds = [];


    allEdgeData.forEach(
        function(edge) {{

            if (
                String(edge.from) ===
                String(parentId)
            ) {{

                const childId =
                    String(edge.to);


                if (
                    childId !== "internet"
                    &&
                    !childIds.includes(
                        childId
                    )
                ) {{

                    childIds.push(
                        childId
                    );

                }}

            }}

        }}
    );


    return allNodeData.filter(
        function(node) {{

            return childIds.includes(
                String(node.id)
            );

        }}
    );

}}


/* =========================================================
   SHOW CHILDREN FOR ROUTER / SWITCH
   ========================================================= */

function showChildrenForParent(
    parentId,
    refit = true
) {{

    const parent =
        allNodeData.find(
            function(node) {{
                return String(node.id) ===
                    String(parentId);
            }}
        );


    if (!parent) {{
        return;
    }}


    if (
        parent.deviceType !== "Router"
        &&
        parent.deviceType !== "Switch"
    ) {{

        return;

    }}


    selectedParentId =
        String(parentId);


    const children =
        getChildren(parentId);


    const panel =
        document.getElementById(
            "childPanel"
        );


    const title =
        document.getElementById(
            "childPanelTitle"
        );


    const subtitle =
        document.getElementById(
            "childPanelSubtitle"
        );


    const summary =
        document.getElementById(
            "childSummary"
        );


    const list =
        document.getElementById(
            "childList"
        );


    const parentName =
        parent.label ||
        parent.hostname ||
        parent.ip ||
        parent.deviceType;


    title.textContent =
        parentName;


    subtitle.textContent =
        parent.deviceType +
        " • Direct children";


    summary.textContent =
        "Connected devices: " +
        children.length;


    list.innerHTML = "";


    if (children.length === 0) {{

        list.innerHTML =
            '<div class="child-empty">' +
            'No direct child devices are ' +
            'present in the current topology.' +
            '<br><br>' +
            'The current topology data does not ' +
            'contain a connection from this ' +
            parent.deviceType +
            ' to another device.' +
            '</div>';

    }}
    else {{

        children.forEach(
            function(child) {{

                const status =
                    String(
                        child.deviceStatus ||
                        "offline"
                    ).toLowerCase();


                const isOffline =
                    status === "offline";


                const hostname =
                    child.hostname ||
                    child.label ||
                    child.ip;


                const item =
                    document.createElement(
                        "div"
                    );


                item.className =
                    "child-item";


                item.innerHTML =
                    '<div class="child-info">' +
                        '<div class="child-name">' +
                            escapeHtml(hostname) +
                        '</div>' +
                        '<div class="child-ip">' +
                            escapeHtml(
                                child.ip || child.id
                            ) +
                        '</div>' +
                    '</div>' +

                    '<div class="child-status">' +

                        '<span class="' +
                            'child-status-dot ' +
                            (
                                isOffline
                                    ? "child-status-offline"
                                    : "child-status-online"
                            ) +
                        '"></span>' +

                        (
                            isOffline
                                ? "Offline"
                                : "Online"
                        ) +

                    '</div>';


                item.addEventListener(
                    "click",
                    function() {{

                        if (
                            child.id !==
                            "internet"
                        ) {{

                            window.location.href =
                                "/device/" +
                                child.id +
                                "/";

                        }}

                    }}
                );


                list.appendChild(
                    item
                );

            }}
        );

    }}


    panel.style.display =
        "block";


    /*
     * Highlight parent and children.
     */

    const highlightIds =
        new Set(
            children.map(
                function(child) {{
                    return String(
                        child.id
                    );
                }}
            )
        );


    highlightIds.add(
        String(parentId)
    );


    const updatedNodes =
        allNodeData
            .filter(
                function(node) {{

                    return nodes.get(
                        node.id
                    ) !== null;

                }}
            )
            .map(
                function(node) {{

                    const isHighlighted =
                        highlightIds.has(
                            String(node.id)
                        );


                    if (isHighlighted) {{

                        return {{

                            ...node,

                            borderWidth:
                                4,

                            shadow: {{

                                enabled: true,

                                color:
                                    "rgba(37,99,235,0.55)",

                                size: 18,

                                x: 0,

                                y: 0

                            }}

                        }};

                    }}


                    return node;

                }}
            );


    nodes.update(
        updatedNodes
    );


    if (refit) {{

        setTimeout(
            function() {{

                network.fit({{

                    nodes:
                        Array.from(
                            highlightIds
                        ),

                    animation: {{

                        duration: 500,

                        easingFunction:
                            "easeInOutQuad"

                    }}

                }});

            }},
            100
        );

    }}

}}


/* =========================================================
   CLOSE CHILD PANEL
   ========================================================= */

function closeChildPanel() {{

    const panel =
        document.getElementById(
            "childPanel"
        );


    panel.style.display =
        "none";


    selectedParentId =
        null;


    /*
     * Restore normal node appearance.
     */

    const restoredNodes =
        allNodeData
            .filter(
                function(node) {{

                    return nodes.get(
                        node.id
                    ) !== null;

                }}
            )
            .map(
                function(node) {{

                    return {{

                        ...node,

                        ...getNodeVisualState(
                            node
                        )

                    }};

                }}
            );


    nodes.clear();

    nodes.add(
        restoredNodes
    );


    applyNodeFilter();

}}


/* =========================================================
   ESCAPE HTML
   ========================================================= */

function escapeHtml(value) {{

    return String(value || "")
        .replace(
            /&/g,
            "&amp;"
        )
        .replace(
            /</g,
            "&lt;"
        )
        .replace(
            />/g,
            "&gt;"
        )
        .replace(
            /"/g,
            "&quot;"
        )
        .replace(
            /'/g,
            "&#039;"
        );

}}


/* =========================================================
   SINGLE CLICK
   ========================================================= */

network.on(
    "click",
    function(params) {{

        if (
            params.nodes.length === 0
        ) {{

            return;

        }}


        const node =
            nodes.get(
                params.nodes[0]
            );


        if (!node) {{

            return;

        }}


        /*
         * Router / Switch:
         * show direct children.
         */

        if (
            node.deviceType === "Router"
            ||
            node.deviceType === "Switch"
        ) {{

            showChildrenForParent(
                node.id
            );

        }}

    }}
);


/* =========================================================
   CLICK EMPTY NETWORK AREA
   ========================================================= */

network.on(
    "click",
    function(params) {{

        if (
            params.nodes.length === 0
            &&
            params.edges.length === 0
        ) {{

            closeChildPanel();

        }}

    }}
);


/* =========================================================
   DOUBLE CLICK DEVICE
   ========================================================= */

network.on(
    "doubleClick",
    function(params) {{

        if (
            params.nodes.length === 0
        ) {{

            return;

        }}


        const node =
            nodes.get(
                params.nodes[0]
            );


        if (!node) {{

            return;

        }}


        if (
            node.id === "internet"
        ) {{

            return;

        }}


        /*
         * Router / Switch:
         * double-click also opens the
         * child view rather than device
         * details.
         */

        if (
            node.deviceType === "Router"
            ||
            node.deviceType === "Switch"
        ) {{

            showChildrenForParent(
                node.id
            );

            return;

        }}


        const ip =
            node.id;


        window.location.href =
            "/device/" +
            ip +
            "/";

    }}
);


/* =========================================================
   LIVE DEVICE STATUS
   ========================================================= */

async function updateDeviceStatus() {{

    try {{

        const response =
            await fetch(
                "/api/topology/status/",
                {{
                    cache: "no-store"
                }}
            );


        if (!response.ok) {{

            console.error(
                "Topology status API returned:",
                response.status
            );

            return;

        }}


        const deviceList =
            await response.json();


        deviceList.forEach(
            function(device) {{

                const originalNode =
                    allNodeData.find(
                        function(item) {{

                            return (
                                String(
                                    item.id
                                ) ===
                                String(
                                    device.ip_address
                                )
                            );

                        }}
                    );


                if (!originalNode) {{

                    return;

                }}


                const status =
                    String(
                        device.status ||
                        "Offline"
                    ).toLowerCase();


                originalNode.deviceStatus =
                    status;

            }}
        );


        applyNodeFilter();


        /*
         * Keep child panel live.
         */

        if (selectedParentId) {{

            showChildrenForParent(
                selectedParentId,
                false
            );

        }}


    }}
    catch (error) {{

        console.error(
            "Topology status update error:",
            error
        );

    }}

}}


/* =========================================================
   INITIAL STATUS UPDATE
   ========================================================= */

updateDeviceStatus();


/* =========================================================
   STATUS UPDATE EVERY 3 SECONDS
   ========================================================= */

setInterval(
    updateDeviceStatus,
    3000
);


/* =========================================================
   INITIAL FIT
   ========================================================= */

setTimeout(
    fitNetwork,
    500
);


</script>

</body>

</html>
"""


    # ========================================================
    # WRITE FILE
    # ========================================================

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(html)

    print(
        f"Topology generated successfully: {OUTPUT_FILE}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    (
        local_ip,
        gateway,
        nodes,
        edges
    ) = build_topology()

    generate_html(
        local_ip,
        gateway,
        nodes,
        edges
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()