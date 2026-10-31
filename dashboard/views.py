import os
import sys
import subprocess
import json

from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.shortcuts import (
    render,
    redirect,
    get_object_or_404
)

from .models import (
    Device,
    DeviceLog,
    DeviceStats,
    DeviceStatsHistory
)

# ============================================================
# SNMP MONITORING MODELS
# ============================================================

from snmp_monitoring.models import (
    SNMPDeviceInfo,
    SNMPCPUHistory,
    SNMPMemoryHistory,
    SNMPDiskHistory
)


# ============================================================
# REMOTE ACCESS SERVER PROCESS
# ============================================================

remote_server_process = None


# ============================================================
# DASHBOARD
# ============================================================

def dashboard(request):

    devices = Device.objects.all().order_by(
        "ip_address"
    )

    total_devices = devices.count()

    online_devices = devices.filter(
        status="Online"
    ).count()

    offline_devices = devices.filter(
        status="Offline"
    ).count()

    context = {
        "devices": devices,
        "total_devices": total_devices,
        "online_devices": online_devices,
        "offline_devices": offline_devices,
    }

    return render(
        request,
        "dashboard/index.html",
        context
    )


# ============================================================
# DEVICE LOGS
# ============================================================

def device_logs(request):

    logs = DeviceLog.objects.select_related(
        "device"
    ).order_by(
        "-timestamp"
    )

    return render(
        request,
        "dashboard/device_logs.html",
        {
            "logs": logs
        }
    )


# ============================================================
# RUN NETWORK SCANNER
# ============================================================

def run_scanner(request):

    if request.method != "POST":

        return redirect(
            "dashboard"
        )

    try:

        base_dir = os.path.dirname(
            os.path.dirname(
                os.path.abspath(__file__)
            )
        )

        scanner_path = os.path.join(
            base_dir,
            "scanner.py"
        )

        print()
        print(
            "========================================"
        )
        print(
            "          NETWORK SCANNER"
        )
        print(
            "========================================"
        )

        print(
            f"Project BASE DIR : {base_dir}"
        )

        print(
            f"Scanner path     : {scanner_path}"
        )

        print(
            f"Scanner exists   : "
            f"{os.path.exists(scanner_path)}"
        )

        print(
            "========================================"
        )
        print()

        if not os.path.isfile(
            scanner_path
        ):

            messages.error(
                request,
                f"scanner.py not found: "
                f"{scanner_path}"
            )

            return redirect(
                "dashboard"
            )

        Device.objects.all().delete()

        print(
            "[SCANNER] Old device records deleted."
        )

        result = subprocess.run(
            [
                sys.executable,
                scanner_path
            ],
            cwd=base_dir,
            capture_output=True,
            text=True
        )

        print()
        print(
            "========== SCANNER OUTPUT =========="
        )

        print(
            result.stdout
        )

        if result.stderr:

            print(
                "========== SCANNER ERROR =========="
            )

            print(
                result.stderr
            )

        print(
            "===================================="
        )
        print()

        if result.returncode != 0:

            messages.error(
                request,
                "Network scanner returned an error."
            )

            return redirect(
                "dashboard"
            )

        print(
            "[SCANNER] Scan completed successfully."
        )

        # ----------------------------------------------------
        # GENERATE TOPOLOGY
        # ----------------------------------------------------

        try:

            print()
            print(
                "========================================"
            )
            print(
                "       GENERATING NETWORK TOPOLOGY"
            )
            print(
                "========================================"
            )

            topology_path = os.path.join(
                base_dir,
                "topology.py"
            )

            print(
                f"Topology path   : {topology_path}"
            )

            print(
                f"Topology exists : "
                f"{os.path.exists(topology_path)}"
            )

            if not os.path.isfile(
                topology_path
            ):

                raise FileNotFoundError(
                    f"topology.py not found: "
                    f"{topology_path}"
                )

            import topology

            topology_data = (
                topology.build_topology()
            )

            topology.generate_html(
                topology_data
            )

            print(
                "[TOPOLOGY] Topology generated successfully."
            )

            print(
                f"[TOPOLOGY] Output file: "
                f"{topology.OUTPUT_FILE}"
            )

            print(
                "========================================"
            )
            print()

        except Exception as topology_error:

            print(
                f"[TOPOLOGY ERROR] "
                f"{topology_error}"
            )

            messages.warning(
                request,
                "Network scan completed, "
                "but topology generation failed."
            )

            return redirect(
                "dashboard"
            )

        messages.success(
            request,
            "Network scan and topology update completed successfully."
        )

    except Exception as e:

        print(
            f"[SCANNER ERROR] {e}"
        )

        messages.error(
            request,
            f"Unable to run scanner: {e}"
        )

    return redirect(
        "dashboard"
    )


# ============================================================
# OPEN TOPOLOGY
# ============================================================

def open_topology(request):

    try:

        base_dir = os.path.dirname(
            os.path.dirname(
                os.path.abspath(__file__)
            )
        )

        topology_html = os.path.join(
            base_dir,
            "topology.html"
        )

        print()
        print(
            "========================================"
        )
        print(
            "          OPENING TOPOLOGY"
        )
        print(
            "========================================"
        )

        print(
            f"Topology file : {topology_html}"
        )

        print(
            f"File exists   : "
            f"{os.path.exists(topology_html)}"
        )

        print(
            "========================================"
        )
        print()

        if not os.path.isfile(
            topology_html
        ):

            messages.warning(
                request,
                "Topology has not been generated yet. "
                "Please press Scan Network first."
            )

            return redirect(
                "dashboard"
            )

        with open(
            topology_html,
            "r",
            encoding="utf-8"
        ) as file:

            html_content = file.read()

        print(
            "[TOPOLOGY] Existing topology loaded."
        )

        print(
            "[TOPOLOGY] No new topology generated."
        )

        return HttpResponse(
            html_content
        )

    except Exception as e:

        print(
            f"[TOPOLOGY ERROR] {e}"
        )

        messages.error(
            request,
            f"Unable to open topology: {e}"
        )

        return redirect(
            "dashboard"
        )


# ============================================================
# DEVICE DETAIL PAGE
# ============================================================

def device_detail(request, ip):

    device = get_object_or_404(
        Device,
        ip_address=ip
    )

    # --------------------------------------------------------
    # CURRENT PING STATISTICS
    # --------------------------------------------------------

    current_stats = DeviceStats.objects.filter(
        device=device
    ).first()

    # --------------------------------------------------------
    # DEVICE LOGS
    # --------------------------------------------------------

    logs = DeviceLog.objects.filter(
        device=device
    ).order_by(
        "-timestamp"
    )[:50]

    # --------------------------------------------------------
    # PING HISTORY
    # --------------------------------------------------------

    history = DeviceStatsHistory.objects.filter(
        device=device
    ).order_by(
        "timestamp"
    )

    # --------------------------------------------------------
    # SNMP DEVICE INFORMATION
    # --------------------------------------------------------

    snmp_info = SNMPDeviceInfo.objects.filter(
        device=device
    ).first()

    # --------------------------------------------------------
    # SNMP CPU HISTORY
    # --------------------------------------------------------

    cpu_history = SNMPCPUHistory.objects.filter(
        device=device
    ).order_by(
        "timestamp"
    )

    # --------------------------------------------------------
    # SNMP MEMORY HISTORY
    # --------------------------------------------------------

    memory_history = SNMPMemoryHistory.objects.filter(
        device=device
    ).order_by(
        "timestamp"
    )

    # --------------------------------------------------------
    # SNMP DISK HISTORY
    # --------------------------------------------------------

    disk_history = SNMPDiskHistory.objects.filter(
        device=device
    ).order_by(
        "timestamp"
    )

    # ========================================================
    # PING LATENCY / PACKET LOSS CHART DATA
    # ========================================================

    latency_labels = []
    latency_values = []

    packet_loss_labels = []
    packet_loss_values = []

    for item in history:

        time_label = item.timestamp.strftime(
            "%H:%M:%S"
        )

        latency_labels.append(
            time_label
        )

        latency_values.append(
            item.latency_ms
        )

        packet_loss_labels.append(
            time_label
        )

        packet_loss_values.append(
            item.packet_loss
        )

    latency_chart_data = {
        "labels": latency_labels,
        "values": latency_values
    }

    packet_loss_chart_data = {
        "labels": packet_loss_labels,
        "values": packet_loss_values
    }

    # ========================================================
    # CPU CHART DATA
    # ========================================================

    cpu_labels = []
    cpu_values = []

    for item in cpu_history:

        cpu_labels.append(
            item.timestamp.strftime(
                "%H:%M:%S"
            )
        )

        cpu_values.append(
            item.utilization
        )

    cpu_chart_data = {
        "labels": cpu_labels,
        "values": cpu_values
    }

    # ========================================================
    # MEMORY CHART DATA
    # ========================================================

    memory_labels = []
    memory_values = []

    for item in memory_history:

        memory_labels.append(
            item.timestamp.strftime(
                "%H:%M:%S"
            )
        )

        memory_values.append(
            item.utilization
        )

    memory_chart_data = {
        "labels": memory_labels,
        "values": memory_values
    }

    # ========================================================
    # DISK CHART DATA
    # ========================================================

    disk_labels = []
    disk_values = []

    for item in disk_history:

        disk_labels.append(
            item.timestamp.strftime(
                "%H:%M:%S"
            )
        )

        disk_values.append(
            item.utilization
        )

    disk_chart_data = {
        "labels": disk_labels,
        "values": disk_values
    }

    # ========================================================
    # CONTEXT
    # ========================================================

    context = {

        # ----------------------------------------------------
        # DEVICE
        # ----------------------------------------------------

        "device": device,

        # ----------------------------------------------------
        # PING DATA
        # ----------------------------------------------------

        "stats": current_stats,

        "current_stats": current_stats,

        "logs": logs,

        "history": history,

        "latency_chart_data": json.dumps(
            latency_chart_data
        ),

        "packet_loss_chart_data": json.dumps(
            packet_loss_chart_data
        ),

        # ----------------------------------------------------
        # SNMP DATA
        # ----------------------------------------------------

        "snmp_info": snmp_info,

        "cpu_history": cpu_history,

        "memory_history": memory_history,

        "disk_history": disk_history,

        "cpu_chart_data": json.dumps(
            cpu_chart_data
        ),

        "memory_chart_data": json.dumps(
            memory_chart_data
        ),

        "disk_chart_data": json.dumps(
            disk_chart_data
        )
    }

    return render(
        request,
        "dashboard/device_detail.html",
        context
    )


# ============================================================
# DEVICE DETAIL API
# ============================================================

def device_detail_api(request, ip):

    device = get_object_or_404(
        Device,
        ip_address=ip
    )

    # --------------------------------------------------------
    # CURRENT PING STATISTICS
    # --------------------------------------------------------

    current_stats = DeviceStats.objects.filter(
        device=device
    ).first()

    # --------------------------------------------------------
    # PING HISTORY
    # --------------------------------------------------------

    history = DeviceStatsHistory.objects.filter(
        device=device
    ).order_by(
        "timestamp"
    )

    # --------------------------------------------------------
    # SNMP DEVICE INFORMATION
    # --------------------------------------------------------

    snmp_info = SNMPDeviceInfo.objects.filter(
        device=device
    ).first()

    # --------------------------------------------------------
    # SNMP CPU HISTORY
    # --------------------------------------------------------

    cpu_history = SNMPCPUHistory.objects.filter(
        device=device
    ).order_by(
        "timestamp"
    )

    # --------------------------------------------------------
    # SNMP MEMORY HISTORY
    # --------------------------------------------------------

    memory_history = SNMPMemoryHistory.objects.filter(
        device=device
    ).order_by(
        "timestamp"
    )

    # --------------------------------------------------------
    # SNMP DISK HISTORY
    # --------------------------------------------------------

    disk_history = SNMPDiskHistory.objects.filter(
        device=device
    ).order_by(
        "timestamp"
    )

    # ========================================================
    # PING CHART DATA
    # ========================================================

    latency_labels = []
    latency_values = []

    packet_loss_labels = []
    packet_loss_values = []

    for item in history:

        time_label = item.timestamp.strftime(
            "%H:%M:%S"
        )

        latency_labels.append(
            time_label
        )

        latency_values.append(
            item.latency_ms
        )

        packet_loss_labels.append(
            time_label
        )

        packet_loss_values.append(
            item.packet_loss
        )

    # ========================================================
    # CPU CHART DATA
    # ========================================================

    cpu_labels = []
    cpu_values = []

    for item in cpu_history:

        cpu_labels.append(
            item.timestamp.strftime(
                "%H:%M:%S"
            )
        )

        cpu_values.append(
            item.utilization
        )

    # ========================================================
    # MEMORY CHART DATA
    # ========================================================

    memory_labels = []
    memory_values = []

    for item in memory_history:

        memory_labels.append(
            item.timestamp.strftime(
                "%H:%M:%S"
            )
        )

        memory_values.append(
            item.utilization
        )

    # ========================================================
    # DISK CHART DATA
    # ========================================================

    disk_labels = []
    disk_values = []

    for item in disk_history:

        disk_labels.append(
            item.timestamp.strftime(
                "%H:%M:%S"
            )
        )

        disk_values.append(
            item.utilization
        )

    # ========================================================
    # DEVICE DATA
    # ========================================================

    device_data = {

        "ip": device.ip_address,

        "mac": (
            device.mac_address
            if device.mac_address
            else "-"
        ),

        "hostname": (
            device.hostname
            if device.hostname
            else "-"
        ),

        "status": device.status,

        "uptime": device.uptime_display,

        "online_since": (
            device.online_since.strftime(
                "%d %b %Y, %H:%M:%S"
            )
            if device.online_since
            else "-"
        ),

        "last_seen": (
            device.last_seen.strftime(
                "%d %b %Y, %H:%M:%S"
            )
            if device.last_seen
            else "-"
        ),
    }

    # ========================================================
    # PING STATISTICS
    # ========================================================

    stats_data = {

        "packets_sent": 0,

        "packets_received": 0,

        "packets_lost": 0,

        "latency_ms": 0,

        "last_poll_time": "-",

        "updated_at": "-",
    }

    if current_stats:

        stats_data = {

            "packets_sent": (
                current_stats.packets_sent
            ),

            "packets_received": (
                current_stats.packets_received
            ),

            "packets_lost": (
                current_stats.packets_lost
            ),

            "latency_ms": (
                current_stats.latency_ms
            ),

            "last_poll_time": (
                current_stats.last_poll_time.strftime(
                    "%d %b %Y, %H:%M:%S"
                )
                if current_stats.last_poll_time
                else "-"
            ),

            "updated_at": (
                current_stats.updated_at.strftime(
                    "%d %b %Y, %H:%M:%S"
                )
            ),
        }

    # ========================================================
    # SNMP INFORMATION
    # ========================================================

    snmp_data = {

        "status": "DOWN",

        "hostname": "-",

        "system_description": "-",

        "system_uptime": "-",

        "object_id": "-",

        "last_updated": "-",
    }

    if snmp_info:

        snmp_data = {

            "status": (
                snmp_info.snmp_status
                if snmp_info.snmp_status
                else "DOWN"
            ),

            "hostname": (
                snmp_info.hostname
                if snmp_info.hostname
                else "-"
            ),

            "system_description": (
                snmp_info.system_description
                if snmp_info.system_description
                else "-"
            ),

            "system_uptime": (
                snmp_info.system_uptime
                if snmp_info.system_uptime
                else "-"
            ),

            "object_id": (
                snmp_info.object_id
                if snmp_info.object_id
                else "-"
            ),

            "last_updated": (
                snmp_info.last_updated.strftime(
                    "%d %b %Y, %H:%M:%S"
                )
                if snmp_info.last_updated
                else "-"
            ),
        }

    # ========================================================
    # LATEST CPU
    # ========================================================

    latest_cpu = None

    if cpu_history.exists():

        latest_cpu = cpu_history.last()

    cpu_data = {

        "utilization": (
            latest_cpu.utilization
            if latest_cpu
            else 0
        ),

        "timestamp": (
            latest_cpu.timestamp.strftime(
                "%d %b %Y, %H:%M:%S"
            )
            if latest_cpu
            else "-"
        )
    }

    # ========================================================
    # LATEST MEMORY
    # ========================================================

    latest_memory = None

    if memory_history.exists():

        latest_memory = memory_history.last()

    memory_data = {

        "total": (
            latest_memory.total
            if latest_memory
            else 0
        ),

        "used": (
            latest_memory.used
            if latest_memory
            else 0
        ),

        "available": (
            latest_memory.available
            if latest_memory
            else 0
        ),

        "utilization": (
            latest_memory.utilization
            if latest_memory
            else 0
        ),

        "timestamp": (
            latest_memory.timestamp.strftime(
                "%d %b %Y, %H:%M:%S"
            )
            if latest_memory
            else "-"
        )
    }

    # ========================================================
    # LATEST DISK INFORMATION
    # ========================================================

    latest_disks = []

    for disk in disk_history:

        latest_disks.append(
            {
                "name": disk.disk_name,

                "total": disk.total,

                "used": disk.used,

                "available": disk.available,

                "utilization": disk.utilization,

                "timestamp": (
                    disk.timestamp.strftime(
                        "%d %b %Y, %H:%M:%S"
                    )
                )
            }
        )

    # ========================================================
    # RESPONSE
    # ========================================================

    response_data = {

        # ----------------------------------------------------
        # DEVICE
        # ----------------------------------------------------

        "device": device_data,

        # ----------------------------------------------------
        # PING
        # ----------------------------------------------------

        "stats": stats_data,

        "latency": {

            "labels": latency_labels,

            "values": latency_values

        },

        "packet_loss": {

            "labels": packet_loss_labels,

            "values": packet_loss_values

        },

        "history": [

            {

                "timestamp": item.timestamp.strftime(
                    "%H:%M:%S"
                ),

                "latency": item.latency_ms,

                "packets_sent": item.packets_sent,

                "packets_received": item.packets_received,

                "packets_lost": item.packets_lost,

                "packet_loss": item.packet_loss,

            }

            for item in history

        ],

        # ----------------------------------------------------
        # SNMP
        # ----------------------------------------------------

        "snmp": snmp_data,

        "cpu": cpu_data,

        "memory": memory_data,

        "disks": latest_disks,

        "cpu_history": {

            "labels": cpu_labels,

            "values": cpu_values

        },

        "memory_history": {

            "labels": memory_labels,

            "values": memory_values

        },

        "disk_history": {

            "labels": disk_labels,

            "values": disk_values

        }
    }

    return JsonResponse(
        response_data
    )


# ============================================================
# DEVICE STATUS API
# ============================================================

def device_status_api(request):

    devices = Device.objects.all().order_by(
        "ip_address"
    )

    device_data = []

    for device in devices:

        uptime = device.uptime_display

        if device.online_since:

            online_since = (
                device.online_since.strftime(
                    "%d %b %Y, %H:%M:%S"
                )
            )

        else:

            online_since = "-"

        if device.last_seen:

            last_seen = (
                device.last_seen.strftime(
                    "%d %b %Y, %H:%M:%S"
                )
            )

        else:

            last_seen = "-"

        device_data.append(
            {

                "ip": device.ip_address,

                "mac": (
                    device.mac_address
                    if device.mac_address
                    else "-"
                ),

                "hostname": (
                    device.hostname
                    if device.hostname
                    else "-"
                ),

                "status": device.status,

                "uptime": uptime,

                "online_since": online_since,

                "last_seen": last_seen,

            }
        )

    total_devices = devices.count()

    online_devices = devices.filter(
        status="Online"
    ).count()

    offline_devices = devices.filter(
        status="Offline"
    ).count()

    response_data = {

        "total": total_devices,

        "online": online_devices,

        "offline": offline_devices,

        "devices": device_data,

    }

    return JsonResponse(
        response_data
    )


# ============================================================
# TOPOLOGY LIVE STATUS API
# ============================================================

def topology_status_api(request):

    devices = Device.objects.all().values(
        "ip_address",
        "status"
    )

    return JsonResponse(
        list(devices),
        safe=False
    )


# ============================================================
# REQUEST REMOTE ACCESS
# ============================================================

def request_remote_access(request, ip):

    global remote_server_process

    try:

        # ----------------------------------------------------
        # VERIFY DEVICE
        # ----------------------------------------------------

        device = get_object_or_404(
            Device,
            ip_address=ip
        )

        # ----------------------------------------------------
        # PROJECT ROOT
        #
        # NMS3/
        # ├── server.py
        # ├── scanner.py
        # ├── topology.py
        # └── dashboard/
        #     └── views.py
        #
        # ----------------------------------------------------

        base_dir = os.path.dirname(
            os.path.dirname(
                os.path.abspath(__file__)
            )
        )

        # ----------------------------------------------------
        # SERVER.PY
        # ----------------------------------------------------

        server_path = os.path.join(
            base_dir,
            "server.py"
        )

        print()
        print(
            "========================================"
        )
        print(
            "       NETSHARE REMOTE ACCESS"
        )
        print(
            "========================================"
        )

        print(
            f"Project root : {base_dir}"
        )

        print(
            f"Server path  : {server_path}"
        )

        print(
            f"Server exists: "
            f"{os.path.exists(server_path)}"
        )

        print(
            f"Requested IP : {ip}"
        )

        print(
            f"Python       : {sys.executable}"
        )

        print(
            "========================================"
        )

        # ----------------------------------------------------
        # CHECK SERVER.PY
        # ----------------------------------------------------

        if not os.path.isfile(
            server_path
        ):

            messages.error(
                request,
                f"server.py not found: {server_path}"
            )

            return redirect(
                "dashboard"
            )

        # ----------------------------------------------------
        # CHECK IF OUR SERVER PROCESS IS ALREADY RUNNING
        # ----------------------------------------------------

        if remote_server_process is not None:

            try:

                if remote_server_process.poll() is None:

                    print(
                        "[REMOTE ACCESS] "
                        "server.py is already running."
                    )

                    print(
                        f"[REMOTE ACCESS] PID: "
                        f"{remote_server_process.pid}"
                    )

                    messages.info(
                        request,
                        "Remote access server is already running."
                    )

                    return redirect(
                        "dashboard"
                    )

            except Exception:

                remote_server_process = None

        # ----------------------------------------------------
        # CREATE ENVIRONMENT FOR SERVER.PY
        # ----------------------------------------------------

        child_env = os.environ.copy()

        # Make sure NMS3 project root is available
        # in Python's module search path.

        existing_pythonpath = child_env.get(
            "PYTHONPATH",
            ""
        )

        if existing_pythonpath:

            child_env["PYTHONPATH"] = (
                base_dir
                + os.pathsep
                + existing_pythonpath
            )

        else:

            child_env["PYTHONPATH"] = base_dir

        # ----------------------------------------------------
        # SERVER LOG FILE
        #
        # NMS3/netshare_server.log
        #
        # This records everything printed by server.py.
        # ----------------------------------------------------

        log_path = os.path.join(
            base_dir,
            "netshare_server.log"
        )

        print(
            f"[REMOTE ACCESS] Log file: {log_path}"
        )

        # ----------------------------------------------------
        # OPEN LOG FILE
        # ----------------------------------------------------

        log_file = None

        try:

            log_file = open(
                log_path,
                "a",
                buffering=1,
                encoding="utf-8"
            )

            log_file.write("\n")

            log_file.write(
                "=" * 70 + "\n"
            )

            log_file.write(
                "Remote server launched by Django\n"
            )

            log_file.write(
                f"Python      : {sys.executable}\n"
            )

            log_file.write(
                f"Server      : {server_path}\n"
            )

            log_file.write(
                f"Working dir : {base_dir}\n"
            )

            log_file.write(
                f"Requested IP: {ip}\n"
            )

            log_file.write(
                "=" * 70 + "\n"
            )

            log_file.flush()

            # ------------------------------------------------
            # WINDOWS
            # ------------------------------------------------

            if os.name == "nt":

                creation_flags = (
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    |
                    subprocess.CREATE_NEW_CONSOLE
                )

                remote_server_process = subprocess.Popen(
                    [
                        sys.executable,
                        "-u",
                        server_path
                    ],
                    cwd=base_dir,
                    env=child_env,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    creationflags=creation_flags
                )

            # ------------------------------------------------
            # LINUX / MAC
            # ------------------------------------------------

            else:

                remote_server_process = subprocess.Popen(
                    [
                        sys.executable,
                        "-u",
                        server_path
                    ],
                    cwd=base_dir,
                    env=child_env,
                    stdout=log_file,
                    stderr=subprocess.STDOUT
                )

            # ------------------------------------------------
            # LOG PROCESS INFORMATION
            # ------------------------------------------------

            log_file.write(
                f"PID         : "
                f"{remote_server_process.pid}\n"
            )

            log_file.write(
                "server.py process started.\n"
            )

            log_file.flush()

            print(
                "[REMOTE ACCESS] server.py started."
            )

            print(
                f"[REMOTE ACCESS] PID: "
                f"{remote_server_process.pid}"
            )

        except Exception as launch_error:

            print(
                "[REMOTE ACCESS ERROR] "
                f"Failed to launch server.py: "
                f"{launch_error}"
            )

            if log_file:

                try:

                    log_file.write(
                        "\n"
                        "[LAUNCH ERROR] "
                        f"{type(launch_error).__name__}: "
                        f"{launch_error}\n"
                    )

                    log_file.flush()

                except Exception:
                    pass

            messages.error(
                request,
                "Unable to start remote access server: "
                f"{launch_error}"
            )

            return redirect(
                "dashboard"
            )

        finally:

            # ------------------------------------------------
            # IMPORTANT:
            # We do not keep the Django request holding
            # the log file open.
            # ------------------------------------------------

            if log_file:

                try:
                    log_file.close()

                except Exception:
                    pass

        # ----------------------------------------------------
        # SUCCESS
        #
        # server.py opens its own Tkinter Viewer window.
        #
        # Django does NOT render remote_access.html.
        # ----------------------------------------------------

        messages.success(
            request,
            "Remote access viewer started."
        )

        return redirect(
            "dashboard"
        )

    except Exception as e:

        print(
            f"[REMOTE ACCESS ERROR] "
            f"{type(e).__name__}: {e}"
        )

        messages.error(
            request,
            f"Unable to start remote access: {e}"
        )

        return redirect(
            "dashboard"
        )