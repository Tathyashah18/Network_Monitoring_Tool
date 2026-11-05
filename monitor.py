
import os
import django
import subprocess
import time
import re
import asyncio
import threading

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nms.settings")
    django.setup()

from django.utils import timezone
from django.db import close_old_connections, connections
from dashboard.models import Device, DeviceLog, DeviceStats, DeviceStatsHistory
from snmp import poll_device
from snmp_monitoring.models import SNMPDeviceInfo, SNMPCPUHistory, SNMPMemoryHistory, SNMPDiskHistory

MONITOR_INTERVAL = 5
HOTSPOT_PREFIX = "192.168.137."
_monitor_thread = None
_monitor_lock = threading.Lock()
_stop_event = threading.Event()

def ping_host(ip):
    try:
        result = subprocess.run(["ping", "-n", "1", "-w", "1000", ip], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        output = result.stdout
        if result.returncode == 0:
            match = re.search(r"time[=<]\s*(\d+)\s*ms", output, re.IGNORECASE)
            latency = float(match.group(1)) if match else (0.5 if "<1ms" in output.lower() else 0)
            return "Online", latency
        return "Offline", 0
    except Exception as e:
        print(f"[PING] Error for {ip}: {e}")
        return "Offline", 0

def update_device_stats(device, status, latency):
    stats, _ = DeviceStats.objects.get_or_create(device=device)
    stats.packets_sent += 1
    if status == "Online":
        stats.packets_received += 1
    else:
        stats.packets_lost += 1
    stats.latency_ms = latency
    stats.last_poll_time = timezone.now()
    stats.save()
    packet_loss = (stats.packets_lost / stats.packets_sent) * 100 if stats.packets_sent else 0
    DeviceStatsHistory.objects.create(device=device, latency_ms=latency, packets_sent=stats.packets_sent, packets_received=stats.packets_received, packets_lost=stats.packets_lost, packet_loss=packet_loss)

def update_device(device, new_status, latency):
    old_status = device.status
    now = timezone.now()
    if new_status == "Online":
        if old_status != "Online":
            device.online_since = now
            DeviceLog.objects.create(device=device, status="Online", message="Device came online")
        device.last_seen = now
    elif old_status != "Offline":
        device.last_uptime_seconds = device.uptime_seconds
        device.online_since = None
        DeviceLog.objects.create(device=device, status="Offline", message="Device went offline")
    device.status = new_status
    device.save()
    update_device_stats(device, new_status, latency)

def save_snmp_result(device, result):
    if not result:
        print(f"[SNMP] No result received for {device.ip_address}")
        return
    SNMPDeviceInfo.objects.update_or_create(device=device, defaults={
        "hostname": result.get("hostname"),
        "system_description": result.get("system_description"),
        "system_uptime": result.get("system_uptime"),
        "object_id": result.get("object_id"),
        "snmp_status": result.get("snmp_status", "DOWN")
    })
    cpu = result.get("cpu")
    if cpu is not None:
        try:
            SNMPCPUHistory.objects.create(device=device, utilization=float(cpu))
        except (ValueError, TypeError) as e:
            print(f"[SNMP] CPU save error {device.ip_address}: {e}")
    memory = result.get("memory")
    if memory:
        try:
            SNMPMemoryHistory.objects.create(device=device, total=int(memory.get("total", 0)), used=int(memory.get("used", 0)), available=int(memory.get("available", 0)), utilization=float(memory.get("utilization", 0)))
        except (ValueError, TypeError) as e:
            print(f"[SNMP] Memory save error {device.ip_address}: {e}")
    for disk in result.get("disks", []):
        try:
            SNMPDiskHistory.objects.create(device=device, disk_name=str(disk.get("name", "Unknown Disk")), total=int(disk.get("total", 0)), used=int(disk.get("used", 0)), available=int(disk.get("available", 0)), utilization=float(disk.get("utilization", 0)))
        except (ValueError, TypeError) as e:
            print(f"[SNMP] Disk save error {device.ip_address}: {e}")

async def poll_all_devices(devices):
    if not devices:
        return []
    return await asyncio.gather(*(poll_device(device.ip_address) for device in devices), return_exceptions=True)

def print_snmp_result(device, result):
    if not result:
        return
    print(f"\n[SNMP] {device.ip_address}")
    print(f"  Status   : {result.get('snmp_status')}")
    print(f"  Hostname : {result.get('hostname')}")
    print(f"  CPU      : {result.get('cpu')}")
    memory = result.get("memory")
    if memory:
        print(f"  Memory   : {memory.get('utilization', 0):.2f}%")
    print(f"  Disks    : {len(result.get('disks', []))}")

def main(stop_event=None):
    event = stop_event or threading.Event()
    print("=" * 55)
    print("NETWORK MONITOR STARTED")
    print("=" * 55)
    print(f"Monitoring interval: {MONITOR_INTERVAL} seconds")
    print(f"Monitoring subnet: {HOTSPOT_PREFIX}0/24")
    while not event.is_set():
        cycle_start = time.time()
        close_old_connections()
        try:
            devices = list(Device.objects.filter(ip_address__startswith=HOTSPOT_PREFIX))
            if not devices:
                print("\nNo hotspot devices found in database.")
            else:
                print(f"\n[{timezone.now()}] Checking {len(devices)} hotspot devices...")
                for device in devices:
                    if event.is_set():
                        break
                    status, latency = ping_host(device.ip_address)
                    update_device(device, status, latency)
                    print(f"[PING] {device.ip_address} -> {status} ({latency} ms)")
                if not event.is_set():
                    try:
                        results = asyncio.run(poll_all_devices(devices))
                    except Exception as e:
                        print(f"[SNMP] Polling error: {e}")
                        results = []
                    for device, result in zip(devices, results):
                        if isinstance(result, Exception):
                            print(f"[SNMP] {device.ip_address} ERROR: {result}")
                            continue
                        try:
                            save_snmp_result(device, result)
                            print_snmp_result(device, result)
                        except Exception as e:
                            print(f"[SNMP] Database error {device.ip_address}: {e}")
        except Exception as e:
            print(f"\nMAIN MONITOR ERROR: {e}")
        finally:
            connections.close_all()
        elapsed = time.time() - cycle_start
        event.wait(max(0, MONITOR_INTERVAL - elapsed))
    print("\nNETWORK MONITOR STOPPED")

def start_monitor():
    global _monitor_thread
    with _monitor_lock:
        if _monitor_thread and _monitor_thread.is_alive():
            print("[MONITOR] Already running.")
            return
        _stop_event.clear()
        _monitor_thread = threading.Thread(target=main, args=(_stop_event,), name="NMS-Monitor", daemon=True)
        _monitor_thread.start()
        print("[MONITOR] Background thread started.")

def stop_monitor():
    _stop_event.set()
    if _monitor_thread and _monitor_thread.is_alive():
        _monitor_thread.join(timeout=10)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        _stop_event.set()
        print("\nMonitoring stopped.")
