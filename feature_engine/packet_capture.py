
from pathlib import Path
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


def capture_live(interface, callback, duration=None, packet_filter=None):
    """
    Capture live packets from a selected interface.

    interface: Scapy interface name or identifier
    callback: function called for every captured packet
    duration: capture duration in seconds, None means continuous
    packet_filter: optional BPF filter
    """
    print(f"\nStarting live capture on: {interface}")

    try:
        sniff(
            iface=interface,
            prn=callback,
            store=False,
            timeout=duration,
            filter=packet_filter
        )
    except PermissionError:
        raise RuntimeError(
            "Permission denied. Run PowerShell as Administrator."
        )
    except OSError as error:
        raise RuntimeError(
            f"Live capture failed: {error}. "
            "Check that Npcap is installed and the interface is valid."
        )

    print("Live capture completed.")


def read_pcap(file_path, callback):
    """
    Read packets from an existing PCAP or PCAPNG file.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Capture file not found: {path}")

    if not path.is_file():
        raise ValueError(f"Capture path is not a file: {path}")

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
