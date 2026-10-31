import os
import django
import subprocess
import time
import re
import asyncio


# ---------------------------------------------------------
# DJANGO SETUP
# ---------------------------------------------------------

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nms.settings")

django.setup()


# ---------------------------------------------------------
# IMPORTS
# ---------------------------------------------------------

from django.utils import timezone

from dashboard.models import (
    Device,
    DeviceLog,
    DeviceStats,
    DeviceStatsHistory,
)

from snmp import poll_device

from snmp_monitoring.models import (
    SNMPDeviceInfo,
    SNMPCPUHistory,
    SNMPMemoryHistory,
    SNMPDiskHistory,
)


# ---------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------

MONITOR_INTERVAL = 5


# ---------------------------------------------------------
# PING
# ---------------------------------------------------------

def ping_host(ip):

    try:

        result = subprocess.run(
            ["ping", "-n", "1", "-w", "1000", ip],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        output = result.stdout

        if result.returncode == 0:

            match = re.search(
                r"time[=<]\s*(\d+)\s*ms",
                output,
                re.IGNORECASE
            )

            if match:
                latency = float(match.group(1))

            elif "<1ms" in output.lower():
                latency = 0.5

            else:
                latency = 0

            return "Online", latency

        return "Offline", 0

    except Exception as e:

        print(f"Ping error for {ip}: {e}")

        return "Offline", 0


# ---------------------------------------------------------
# UPDATE PING STATISTICS
# ---------------------------------------------------------

def update_device_stats(device, status, latency):

    stats, created = DeviceStats.objects.get_or_create(
        device=device
    )

    stats.packets_sent += 1

    if status == "Online":

        stats.packets_received += 1

    else:

        stats.packets_lost += 1

    stats.latency_ms = latency
    stats.last_poll_time = timezone.now()

    stats.save()

    total_sent = stats.packets_sent
    total_received = stats.packets_received
    total_lost = stats.packets_lost

    if total_sent > 0:

        packet_loss = (
            total_lost / total_sent
        ) * 100

    else:

        packet_loss = 0

    DeviceStatsHistory.objects.create(
        device=device,
        latency_ms=latency,
        packets_sent=total_sent,
        packets_received=total_received,
        packets_lost=total_lost,
        packet_loss=packet_loss
    )


# ---------------------------------------------------------
# UPDATE DEVICE STATUS
# ---------------------------------------------------------

def update_device(device, new_status, latency):

    old_status = device.status

    # -----------------------------------------------------
    # ONLINE
    # -----------------------------------------------------

    if new_status == "Online":

        if old_status != "Online":

            device.online_since = timezone.now()

            DeviceLog.objects.create(
                device=device,
                status="Online",
                message="Device came online"
            )

        device.last_seen = timezone.now()

    # -----------------------------------------------------
    # OFFLINE
    # -----------------------------------------------------

    else:

        if old_status != "Offline":

            # Store last known uptime
            device.last_uptime_seconds = (
                device.uptime_seconds
            )

            device.online_since = None

            DeviceLog.objects.create(
                device=device,
                status="Offline",
                message="Device went offline"
            )

    device.status = new_status

    device.save()

    # Update ping statistics
    update_device_stats(
        device,
        new_status,
        latency
    )


# ---------------------------------------------------------
# SAVE SNMP RESULT
# ---------------------------------------------------------

def save_snmp_result(device, result):

    if not result:

        print(
            f"[SNMP] No result received for "
            f"{device.ip_address}"
        )

        return

    # -----------------------------------------------------
    # CURRENT SNMP DEVICE INFORMATION
    # -----------------------------------------------------

    SNMPDeviceInfo.objects.update_or_create(

        device=device,

        defaults={
            "hostname": result.get("hostname"),
            "system_description": result.get(
                "system_description"
            ),
            "system_uptime": result.get(
                "system_uptime"
            ),
            "object_id": result.get(
                "object_id"
            ),
            "snmp_status": result.get(
                "snmp_status",
                "DOWN"
            ),
        }
    )

    # -----------------------------------------------------
    # CPU HISTORY
    # -----------------------------------------------------

    cpu = result.get("cpu")

    if cpu is not None:

        try:

            SNMPCPUHistory.objects.create(
                device=device,
                utilization=float(cpu)
            )

        except (ValueError, TypeError) as e:

            print(
                f"[SNMP] CPU save error "
                f"{device.ip_address}: {e}"
            )

    # -----------------------------------------------------
    # MEMORY HISTORY
    # -----------------------------------------------------

    memory = result.get("memory")

    if memory:

        try:

            SNMPMemoryHistory.objects.create(
                device=device,
                total=int(memory.get("total", 0)),
                used=int(memory.get("used", 0)),
                available=int(
                    memory.get("available", 0)
                ),
                utilization=float(
                    memory.get("utilization", 0)
                )
            )

        except (ValueError, TypeError) as e:

            print(
                f"[SNMP] Memory save error "
                f"{device.ip_address}: {e}"
            )

    # -----------------------------------------------------
    # DISK HISTORY
    # -----------------------------------------------------

    disks = result.get("disks", [])

    for disk in disks:

        try:

            SNMPDiskHistory.objects.create(

                device=device,

                disk_name=str(
                    disk.get(
                        "name",
                        "Unknown Disk"
                    )
                ),

                total=int(
                    disk.get("total", 0)
                ),

                used=int(
                    disk.get("used", 0)
                ),

                available=int(
                    disk.get("available", 0)
                ),

                utilization=float(
                    disk.get("utilization", 0)
                )
            )

        except (ValueError, TypeError) as e:

            print(
                f"[SNMP] Disk save error "
                f"{device.ip_address}: {e}"
            )


# ---------------------------------------------------------
# POLL ALL DEVICES WITH SNMP
# ---------------------------------------------------------

async def poll_all_devices(devices):

    tasks = []

    for device in devices:

        tasks.append(
            poll_device(
                device.ip_address
            )
        )

    if not tasks:

        return []

    results = await asyncio.gather(
        *tasks,
        return_exceptions=True
    )

    return results


# ---------------------------------------------------------
# PRINT SNMP RESULT
# ---------------------------------------------------------

def print_snmp_result(device, result):

    if not result:
        return

    print(
        f"\n[SNMP] {device.ip_address}"
    )

    print(
        f"  Status    : "
        f"{result.get('snmp_status')}"
    )

    print(
        f"  Hostname  : "
        f"{result.get('hostname')}"
    )

    print(
        f"  CPU       : "
        f"{result.get('cpu')}"
    )

    memory = result.get("memory")

    if memory:

        print(
            f"  Memory    : "
            f"{memory.get('utilization', 0):.2f}%"
        )

    disks = result.get("disks", [])

    print(
        f"  Disks     : "
        f"{len(disks)}"
    )


# ---------------------------------------------------------
# MAIN MONITORING LOOP
# ---------------------------------------------------------

def main():

    print("=" * 60)
    print("NETWORK MONITOR STARTED")
    print("=" * 60)

    print(
        f"Monitoring interval: "
        f"{MONITOR_INTERVAL} seconds"
    )

    while True:

        cycle_start = time.time()

        try:

            # -------------------------------------------------
            # GET DEVICES FROM DATABASE
            # -------------------------------------------------

            devices = list(
                Device.objects.all()
            )

            if not devices:

                print(
                    "\nNo devices found in database."
                )

                time.sleep(
                    MONITOR_INTERVAL
                )

                continue

            print(
                f"\n[{timezone.now()}] "
                f"Checking {len(devices)} devices..."
            )

            # -------------------------------------------------
            # PING MONITORING
            # -------------------------------------------------

            for device in devices:

                status, latency = ping_host(
                    device.ip_address
                )

                update_device(
                    device,
                    status,
                    latency
                )

                print(
                    f"[PING] "
                    f"{device.ip_address} "
                    f"-> {status} "
                    f"({latency} ms)"
                )

            # -------------------------------------------------
            # SNMP MONITORING
            # -------------------------------------------------

            try:

                snmp_results = asyncio.run(
                    poll_all_devices(devices)
                )

            except Exception as e:

                print(
                    f"[SNMP] Polling error: {e}"
                )

                snmp_results = []

            # -------------------------------------------------
            # SAVE SNMP DATA
            # -------------------------------------------------

            for device, result in zip(
                devices,
                snmp_results
            ):

                if isinstance(
                    result,
                    Exception
                ):

                    print(
                        f"[SNMP] "
                        f"{device.ip_address} "
                        f"ERROR: {result}"
                    )

                    continue

                try:

                    save_snmp_result(
                        device,
                        result
                    )

                    print_snmp_result(
                        device,
                        result
                    )

                except Exception as e:

                    print(
                        f"[SNMP] Database error "
                        f"{device.ip_address}: {e}"
                    )

            # -------------------------------------------------
            # WAIT
            # -------------------------------------------------

            elapsed = (
                time.time() - cycle_start
            )

            sleep_time = max(
                0,
                MONITOR_INTERVAL - elapsed
            )

            time.sleep(sleep_time)

        except KeyboardInterrupt:

            print(
                "\nMonitoring stopped."
            )

            break

        except Exception as e:

            print(
                f"\nMAIN MONITOR ERROR: {e}"
            )

            time.sleep(
                MONITOR_INTERVAL
            )


# ---------------------------------------------------------
# START
# ---------------------------------------------------------

if __name__ == "__main__":
    main()