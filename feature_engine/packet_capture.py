
from pathlib import Path
from queue import Queue, Empty
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
    Capture packets in a background thread and process them
    sequentially in the calling thread.

    The capture thread only places packets into a thread-safe queue.
    The calling thread processes packets and expires idle flows.

    duration=None means continuous capture.
    """

    print(f"\nStarting live capture on: {interface}")
    print("Press CTRL+C to stop safely.")

    packet_queue = Queue()

    # The capture thread only enqueues packets.
    sniffer = AsyncSniffer(
        iface=interface,
        prn=packet_queue.put,
        store=False,
        filter=packet_filter,
    )

    started = False
    start_time = time.monotonic()
    last_status_time = start_time

    def process_queued_packets():
        """Process all packets currently waiting in the queue."""

        processed = 0

        while True:
            try:
                packet = packet_queue.get_nowait()
            except Empty:
                break

            try:
                callback(packet)
                processed += 1
            finally:
                packet_queue.task_done()

        return processed

    try:
        sniffer.start()
        started = True

        while True:

            if duration is not None:
                elapsed = time.monotonic() - start_time

                if elapsed >= duration:
                    break

            # Wait briefly for a packet.
            try:
                packet = packet_queue.get(timeout=0.25)

                try:
                    callback(packet)
                finally:
                    packet_queue.task_done()

            except Empty:
                pass

            # Process any additional packets already queued.
            process_queued_packets()

            # Flow expiration happens in this same thread.
            if idle_callback is not None:
                idle_callback()

            # Report queue backlog periodically.
            current_time = time.monotonic()

            if current_time - last_status_time >= 10:
                logger_backlog = packet_queue.qsize()

                print(
                    f"Capture running | "
                    f"Queued packets: {logger_backlog}"
                )

                last_status_time = current_time

    except KeyboardInterrupt:
        print("\nLive capture stopped by user.")

    finally:

        # Stop packet reception before draining the queue.
        if started and sniffer.running:
            sniffer.stop(join=True)

        # Process all packets captured before shutdown.
        process_queued_packets()

        if idle_callback is not None:
            idle_callback()

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
