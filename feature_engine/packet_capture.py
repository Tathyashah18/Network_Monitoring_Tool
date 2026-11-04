
from pathlib import Path
import time

from scapy.all import sniff, PcapReader, conf


def list_interfaces():
    """Display network interfaces recognised by Scapy."""
    print("\nAvailable network interfaces:\n")

    for interface in conf.ifaces.values():
        print(
            f"Name: {interface.name} | "
            f"Description: {interface.description} | "
            f"GUID: {interface.guid}"
        )


def capture_live(
    interface,
    callback,
    duration=None,
    packet_filter=None,
    idle_callback=None,
):
    """
    Capture live packets.

    duration=None means continuous capture.
    idle_callback runs approximately once per second.
    """

    print(f"\nStarting live capture on: {interface}")
    print("Press CTRL+C to stop safely.")

    start_time = time.monotonic()
    packet_count = 0

    try:
        while True:
            if duration is None:
                timeout = 1
            else:
                remaining = duration - (
                    time.monotonic() - start_time
                )

                if remaining <= 0:
                    break

                timeout = min(1, remaining)

            captured = sniff(
                iface=interface,
                prn=callback,
                store=False,
                timeout=timeout,
                filter=packet_filter,
            )

            packet_count += len(captured)

            if idle_callback is not None:
                idle_callback()

    except KeyboardInterrupt:
        print("\nLive capture stopped by user.")

    except PermissionError as error:
        raise RuntimeError(
            "Permission denied. Run PowerShell as Administrator."
        ) from error

    except Exception as error:
        raise RuntimeError(
            f"Live capture failed: {error}. "
            "Check Npcap and the selected interface."
        ) from error

    print(f"Live packets captured: {packet_count}")


def read_pcap(file_path, callback):
    """Read packets from an existing PCAP or PCAPNG file."""

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Capture file not found: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Capture path is not a file: {path}"
        )

    packet_count = 0

    print(f"\nReading capture file: {path}")

    try:
        with PcapReader(str(path)) as capture:
            for packet in capture:
                callback(packet)
                packet_count += 1

    except Exception as error:
        raise RuntimeError(
            f"Failed to read capture file: {error}"
        ) from error

    print(f"Packets processed: {packet_count}")

    return packet_count
