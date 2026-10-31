import asyncio
import subprocess

from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    get_cmd,
    walk_cmd
)


# ============================================================
# SNMP CONFIGURATION
# ============================================================

COMMUNITY = "public"
PORT = 161

SNMP_TIMEOUT = 2
SNMP_RETRIES = 1


# ============================================================
# MANUAL TEST DEVICES
# ============================================================
# These are ONLY used when running:
#
#     python snmp.py
#
# Django monitor.py will NOT use this list.
# It will get IP addresses from the Device table.

TEST_IPS = [
    "192.168.1.105",
    "192.168.1.100",
    "192.168.1.107",
    "192.168.1.108",
]

POLL_INTERVAL = 5


# ============================================================
# PING / REACHABILITY
# ============================================================

async def ping_host(ip):

    try:

        process = await asyncio.create_subprocess_exec(
            "ping",
            "-n", "1",
            "-w", "2000",
            ip,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )

        returncode = await process.wait()

        return returncode == 0

    except Exception as e:

        print(f"[{ip}] Ping Exception: {e}")

        return False


# ============================================================
# SNMP GET
# ============================================================

async def snmp_get(ip, oid):

    try:

        transport = await UdpTransportTarget.create(
            (ip, PORT),
            timeout=SNMP_TIMEOUT,
            retries=SNMP_RETRIES
        )

        (
            errorIndication,
            errorStatus,
            errorIndex,
            varBinds
        ) = await get_cmd(

            SnmpEngine(),

            CommunityData(
                COMMUNITY,
                mpModel=1
            ),

            transport,

            ContextData(),

            ObjectType(
                ObjectIdentity(oid)
            )
        )

        if errorIndication:

            return None

        if errorStatus:

            return None

        for varBind in varBinds:

            return str(varBind[1])

        return None

    except Exception as e:

        print(
            f"[{ip}] SNMP GET Exception "
            f"[{oid}]: {e}"
        )

        return None


# ============================================================
# SNMP WALK
# ============================================================

async def snmp_walk(ip, oid):

    values = []

    try:

        transport = await UdpTransportTarget.create(
            (ip, PORT),
            timeout=SNMP_TIMEOUT,
            retries=SNMP_RETRIES
        )

        async for (
            errorIndication,
            errorStatus,
            errorIndex,
            varBinds
        ) in walk_cmd(

            SnmpEngine(),

            CommunityData(
                COMMUNITY,
                mpModel=1
            ),

            transport,

            ContextData(),

            ObjectType(
                ObjectIdentity(oid)
            ),

            lexicographicMode=False

        ):

            if errorIndication:

                break

            if errorStatus:

                break

            for varBind in varBinds:

                values.append(
                    (
                        str(varBind[0]),
                        str(varBind[1])
                    )
                )

    except Exception as e:

        print(
            f"[{ip}] SNMP WALK Exception "
            f"[{oid}]: {e}"
        )

    return values


# ============================================================
# CPU UTILIZATION
# ============================================================
#
# hrProcessorLoad
#
# OID:
# 1.3.6.1.2.1.25.3.3.1.2
#
# ============================================================

async def get_cpu_utilization(ip):

    cpu_values = []

    try:

        values = await snmp_walk(
            ip,
            "1.3.6.1.2.1.25.3.3.1.2"
        )

        for oid, value in values:

            try:

                cpu_load = float(value)

                cpu_values.append(
                    cpu_load
                )

            except (ValueError, TypeError):

                continue

        if cpu_values:

            return (
                sum(cpu_values)
                / len(cpu_values)
            )

        return None

    except Exception as e:

        print(
            f"[{ip}] CPU Exception: {e}"
        )

        return None


# ============================================================
# MEMORY UTILIZATION
# ============================================================
#
# hrMemorySize:
#
# 1.3.6.1.2.1.25.2.2.0
#
# hrStorageTable:
#
# 1.3.6.1.2.1.25.2.3.1
#
# Column 4 = Allocation Units
# Column 5 = Size
# Column 6 = Used
#
# ============================================================

async def get_memory_utilization(ip):

    try:

        # ----------------------------------------------------
        # Get total physical memory
        # ----------------------------------------------------

        memory_size = await snmp_get(
            ip,
            "1.3.6.1.2.1.25.2.2.0"
        )

        if memory_size is None:

            return None

        memory_size = int(
            memory_size
        )

        # hrMemorySize is in KB
        expected_memory = (
            memory_size * 1024
        )

        # ----------------------------------------------------
        # Storage table
        # ----------------------------------------------------

        values = await snmp_walk(
            ip,
            "1.3.6.1.2.1.25.2.3.1"
        )

        if not values:

            return None

        storage_units = {}
        storage_sizes = {}
        storage_used = {}

        for oid, value in values:

            try:

                index = oid.split(".")[-1]

                if ".25.2.3.1.4." in oid:

                    storage_units[index] = int(
                        value
                    )

                elif ".25.2.3.1.5." in oid:

                    storage_sizes[index] = int(
                        value
                    )

                elif ".25.2.3.1.6." in oid:

                    storage_used[index] = int(
                        value
                    )

            except (ValueError, TypeError):

                continue

        # ----------------------------------------------------
        # Find RAM entry
        # ----------------------------------------------------

        total_bytes = None
        used_bytes = None

        for index in storage_sizes:

            if index not in storage_units:

                continue

            if index not in storage_used:

                continue

            allocation_unit = (
                storage_units[index]
            )

            size = (
                storage_sizes[index]
            )

            used = (
                storage_used[index]
            )

            if allocation_unit <= 0:

                continue

            total = (
                allocation_unit
                * size
            )

            used = (
                allocation_unit
                * used
            )

            # Allow 80%-120% difference
            # because different operating systems
            # may report slightly different values.

            if (
                expected_memory * 0.8
                <= total
                <= expected_memory * 1.2
            ):

                total_bytes = total
                used_bytes = used

                break

        if total_bytes is None:

            return None

        # ----------------------------------------------------
        # Calculate memory
        # ----------------------------------------------------

        available_bytes = max(
            0,
            total_bytes - used_bytes
        )

        if total_bytes > 0:

            utilization = (
                used_bytes
                / total_bytes
            ) * 100

        else:

            utilization = 0

        return {

            "total": total_bytes,

            "used": used_bytes,

            "available": available_bytes,

            "utilization": utilization

        }

    except Exception as e:

        print(
            f"[{ip}] Memory Exception: {e}"
        )

        return None


# ============================================================
# DISK UTILIZATION
# ============================================================

async def get_disk_utilization(ip):

    try:

        values = await snmp_walk(
            ip,
            "1.3.6.1.2.1.25.2.3.1"
        )

        if not values:

            return []

        storage_types = {}
        storage_names = {}
        storage_units = {}
        storage_sizes = {}
        storage_used = {}

        # ----------------------------------------------------
        # Parse storage table
        # ----------------------------------------------------

        for oid, value in values:

            try:

                index = oid.split(".")[-1]

                if ".25.2.3.1.2." in oid:

                    storage_types[index] = value

                elif ".25.2.3.1.3." in oid:

                    storage_names[index] = value

                elif ".25.2.3.1.4." in oid:

                    storage_units[index] = int(
                        value
                    )

                elif ".25.2.3.1.5." in oid:

                    storage_sizes[index] = int(
                        value
                    )

                elif ".25.2.3.1.6." in oid:

                    storage_used[index] = int(
                        value
                    )

            except (ValueError, TypeError):

                continue

        # ----------------------------------------------------
        # Build disk list
        # ----------------------------------------------------

        disks = []

        for index in storage_sizes:

            if index not in storage_units:

                continue

            if index not in storage_used:

                continue

            if index not in storage_names:

                continue

            allocation_unit = (
                storage_units[index]
            )

            total_units = (
                storage_sizes[index]
            )

            used_units = (
                storage_used[index]
            )

            name = (
                storage_names[index]
            )

            if allocation_unit <= 0:

                continue

            total_bytes = (
                allocation_unit
                * total_units
            )

            used_bytes = (
                allocation_unit
                * used_units
            )

            available_bytes = max(
                0,
                total_bytes - used_bytes
            )

            if total_bytes <= 0:

                continue

            utilization = (
                used_bytes
                / total_bytes
            ) * 100

            name_lower = name.lower()

            # ------------------------------------------------
            # Ignore memory / virtual memory
            # ------------------------------------------------

            if (
                "physical memory" in name_lower
                or "virtual memory" in name_lower
                or "ram" in name_lower
                or "swap" in name_lower
            ):

                continue

            disks.append({

                "name": name,

                "total": total_bytes,

                "used": used_bytes,

                "available": available_bytes,

                "utilization": utilization

            })

        return disks

    except Exception as e:

        print(
            f"[{ip}] Disk Exception: {e}"
        )

        return []


# ============================================================
# POLL ONE DEVICE
# ============================================================
#
# THIS IS THE MAIN FUNCTION THAT monitor.py WILL USE.
#
# monitor.py will call:
#
#     await poll_device(ip)
#
# ============================================================

async def poll_device(ip):

    # --------------------------------------------------------
    # Default result
    # --------------------------------------------------------

    result = {

        "ip": ip,

        "reachable": False,

        "latency": 0,

        "hostname": None,

        "system_description": None,

        "system_uptime": None,

        "object_id": None,

        "snmp_status": "DOWN",

        "cpu": None,

        "memory": None,

        "disks": []

    }

    # --------------------------------------------------------
    # Reachability
    # --------------------------------------------------------

    reachable = await ping_host(
        ip
    )

    result["reachable"] = reachable

    # --------------------------------------------------------
    # Get latency
    # --------------------------------------------------------
    #
    # We use a normal Windows ping here to obtain latency.
    #
    # This is separate from the reachability check above.
    #
    # --------------------------------------------------------

    if reachable:

        try:

            process = await asyncio.create_subprocess_exec(

                "ping",

                "-n", "1",

                "-w", "2000",

                ip,

                stdout=asyncio.subprocess.PIPE,

                stderr=asyncio.subprocess.DEVNULL,

            )

            stdout, _ = await process.communicate()

            output = stdout.decode(
                errors="ignore"
            )

            import re

            match = re.search(
                r"time[=<]\s*(\d+)\s*ms",
                output,
                re.IGNORECASE
            )

            if match:

                result["latency"] = float(
                    match.group(1)
                )

            elif "<1ms" in output.lower():

                result["latency"] = 0.5

        except Exception:

            result["latency"] = 0

    # --------------------------------------------------------
    # Basic system information
    # --------------------------------------------------------

    sys_descr_oid = (
        "1.3.6.1.2.1.1.1.0"
    )

    sys_uptime_oid = (
        "1.3.6.1.2.1.1.3.0"
    )

    sys_name_oid = (
        "1.3.6.1.2.1.1.5.0"
    )

    sys_object_id_oid = (
        "1.3.6.1.2.1.1.2.0"
    )

    # --------------------------------------------------------
    # Get all basic values simultaneously
    # --------------------------------------------------------

    (
        system_description,
        system_uptime,
        hostname,
        object_id
    ) = await asyncio.gather(

        snmp_get(
            ip,
            sys_descr_oid
        ),

        snmp_get(
            ip,
            sys_uptime_oid
        ),

        snmp_get(
            ip,
            sys_name_oid
        ),

        snmp_get(
            ip,
            sys_object_id_oid
        )

    )

    result["system_description"] = (
        system_description
    )

    result["system_uptime"] = (
        system_uptime
    )

    result["hostname"] = (
        hostname
    )

    result["object_id"] = (
        object_id
    )

    # --------------------------------------------------------
    # Determine SNMP status
    # --------------------------------------------------------
    #
    # Do NOT depend only on hostname.
    #
    # Some SNMP devices may respond to system OIDs even
    # if sysName is unavailable.
    #
    # --------------------------------------------------------

    if any([
        system_description,
        system_uptime,
        hostname,
        object_id
    ]):

        result["snmp_status"] = "UP"

    else:

        result["snmp_status"] = "DOWN"

    # --------------------------------------------------------
    # CPU / Memory / Disk
    # --------------------------------------------------------
    #
    # Only collect these if SNMP is responding.
    #
    # --------------------------------------------------------

    if result["snmp_status"] == "UP":

        cpu, memory, disks = await asyncio.gather(

            get_cpu_utilization(ip),

            get_memory_utilization(ip),

            get_disk_utilization(ip)

        )

        result["cpu"] = cpu

        result["memory"] = memory

        result["disks"] = disks

    return result


# ============================================================
# PRINT ONE DEVICE
# ============================================================

def print_device(result):

    ip = result["ip"]

    print()

    print("=" * 70)

    print("SNMP DEVICE MONITORING")

    print(
        f"IP Address: {ip}"
    )

    print("=" * 70)

    # ========================================================
    # STATUS
    # ========================================================

    print("\n--- STATUS ---")

    print(
        "Reachability Status :",
        "UP"
        if result["reachable"]
        else "DOWN"
    )

    print(
        "SNMP Status         :",
        result["snmp_status"]
    )

    print(
        "Ping Latency        :",
        f"{result['latency']} ms"
    )

    # ========================================================
    # DEVICE INFORMATION
    # ========================================================

    print(
        "\n--- DEVICE INFORMATION ---"
    )

    print(
        "Hostname            :",
        result["hostname"] or "N/A"
    )

    print(
        "Device Name         :",
        result["hostname"] or "N/A"
    )

    print(
        "Device Type         :",
        "PC / Workstation"
    )

    print(
        "Manufacturer        :",
        "See System Description"
    )

    print(
        "OS / Firmware       :",
        result["system_description"]
        or "N/A"
    )

    print(
        "OS Version          :",
        "See System Description"
    )

    print(
        "System Description  :",
        result["system_description"]
        or "N/A"
    )

    print(
        "System Uptime       :",
        result["system_uptime"]
        or "N/A"
    )

    print(
        "SNMP Version        :",
        "SNMPv2c"
    )

    print(
        "SNMP Port           :",
        PORT
    )

    print(
        "SNMP Object ID      :",
        result["object_id"]
        or "N/A"
    )

    # ========================================================
    # CPU
    # ========================================================

    print("\n--- CPU ---")

    cpu = result["cpu"]

    if cpu is not None:

        print(
            f"CPU Utilization     : "
            f"{cpu:.2f}%"
        )

    else:

        print(
            "CPU Utilization     : N/A"
        )

    # ========================================================
    # MEMORY
    # ========================================================

    print("\n--- MEMORY ---")

    memory = result["memory"]

    if memory is not None:

        total_gb = (
            memory["total"]
            / (1024 ** 3)
        )

        used_gb = (
            memory["used"]
            / (1024 ** 3)
        )

        available_gb = (
            memory["available"]
            / (1024 ** 3)
        )

        print(
            f"Total Memory       : "
            f"{total_gb:.2f} GB"
        )

        print(
            f"Used Memory        : "
            f"{used_gb:.2f} GB"
        )

        print(
            f"Available Memory   : "
            f"{available_gb:.2f} GB"
        )

        print(
            f"Memory Utilization : "
            f"{memory['utilization']:.2f}%"
        )

    else:

        print(
            "Total Memory       : N/A"
        )

        print(
            "Used Memory        : N/A"
        )

        print(
            "Available Memory   : N/A"
        )

        print(
            "Memory Utilization : N/A"
        )

    # ========================================================
    # DISK
    # ========================================================

    print("\n--- DISK ---")

    disks = result["disks"]

    if disks:

        for disk in disks:

            total_gb = (
                disk["total"]
                / (1024 ** 3)
            )

            used_gb = (
                disk["used"]
                / (1024 ** 3)
            )

            available_gb = (
                disk["available"]
                / (1024 ** 3)
            )

            print(
                f"\nDrive              : "
                f"{disk['name']}"
            )

            print(
                f"Total Disk Space   : "
                f"{total_gb:.2f} GB"
            )

            print(
                f"Used Disk Space    : "
                f"{used_gb:.2f} GB"
            )

            print(
                f"Available Space    : "
                f"{available_gb:.2f} GB"
            )

            print(
                f"Disk Utilization   : "
                f"{disk['utilization']:.2f}%"
            )

    else:

        print(
            "Disk Information   : N/A"
        )

    print()


# ============================================================
# MANUAL TEST MODE
# ============================================================
#
# This section allows you to continue testing snmp.py
# independently from Django.
#
# Django monitor.py does NOT call this function.
#
# ============================================================

async def manual_test():

    print("=" * 70)

    print(
        "SNMP MANUAL TEST MODE"
    )

    print("=" * 70)

    print()

    print(
        "Available test devices:"
    )

    for number, ip in enumerate(
        TEST_IPS,
        start=1
    ):

        print(
            f"{number}. {ip}"
        )

    print()

    selected = input(
        "Enter device IP: "
    ).strip()

    if not selected:

        print(
            "No IP entered."
        )

        return

    result = await poll_device(
        selected
    )

    print_device(
        result
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            manual_test()
        )

    except KeyboardInterrupt:

        print()

        print(
            "=" * 70
        )

        print(
            "SNMP TEST STOPPED"
        )

        print(
            "=" * 70
        )