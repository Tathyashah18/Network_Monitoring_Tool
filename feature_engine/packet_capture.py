
from pathlib import Path
import queue
import time

from scapy.all import AsyncSniffer, PcapReader, conf


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
    Capture packets in a background thread.

    A thread-safe queue transfers packets to the main thread.
    The callback and idle_callback execute only in the main thread.
    """

    print(f"\nStarting live capture on: {interface}")
    print("Press CTRL+C to stop safely.")

    packet_queue = queue.Queue()

    sniffer = AsyncSniffer(
        iface=interface,
        prn=packet_queue.put,
        store=False,
        filter=packet_filter,
    )

    started = False
    start_time = time.monotonic()

    def process_queued_packets():
        """Process all packets currently waiting in the queue."""

        processed = 0

        while True:
            try:
                packet = packet_queue.get_nowait()
            except queue.Empty:
                break

            callback(packet)
            processed += 1

        return processed

    try:
        sniffer.start()
        started = True

        while True:

            # Process packets in the main thread.
            process_queued_packets()

            # Expire idle flows only after draining the queue.
            if idle_callback is not None:
                idle_callback()

            if duration is not None:
                elapsed = time.monotonic() - start_time

                if elapsed >= duration:
                    break

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nLive capture stopped by user.")

    finally:

        if started:
            try:
                if sniffer.running:
                    sniffer.stop()

                sniffer.join()

            finally:
                # Process packets captured before shutdown.
                process_queued_packets()

    print("Live capture session closed.")


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
