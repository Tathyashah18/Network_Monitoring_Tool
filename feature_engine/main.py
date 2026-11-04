
import argparse
import logging
from pathlib import Path

from .config import FLOW_TIMEOUT_SECONDS, DEFAULT_OUTPUT
from .flow_manager import FlowManager
from .packet_capture import (
    list_interfaces,
    capture_live,
    read_pcap,
)
from .flow_exporter import FlowExporter


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("NMT-Feature-Engine")


class FeatureEngine:

    def __init__(self, output_path):
        self.flow_manager = FlowManager(
            flow_timeout=FLOW_TIMEOUT_SECONDS
        )

        self.exporter = FlowExporter(output_path)

        self.packet_count = 0
        self.exported_flow_count = 0

    def process_packet(self, packet):
        """Process one packet and export expired flows."""

        self.packet_count += 1

        try:
            timestamp = float(packet.time)

            # Export expired flows before processing the new packet.
            expired_flows = self.flow_manager.get_expired_flows(
                timestamp
            )

            if expired_flows:
                self.export_flows(expired_flows)

            self.flow_manager.process_packet(packet)

        except Exception:
            logger.exception(
                "Error processing packet number %d",
                self.packet_count,
            )

    def export_flows(self, flows):
        """Calculate features and export flows."""

        for flow in flows:
            try:
                self.exporter.export_flow(flow)
                self.exported_flow_count += 1

            except Exception:
                logger.exception(
                    "Failed to export flow: %s",
                    flow.flow_id,
                )

    def finish(self):
        """Export remaining flows and close the CSV."""

        try:
            remaining_flows = self.flow_manager.flush_all()

            if remaining_flows:
                self.export_flows(remaining_flows)

        finally:
            self.exporter.close()

        logger.info("Capture processing completed")
        logger.info("Packets processed: %d", self.packet_count)
        logger.info("Flows exported: %d", self.exported_flow_count)


def run_pcap(input_path, output_path):
    """Extract features from an existing capture file."""

    engine = FeatureEngine(output_path)

    try:
        read_pcap(
            file_path=input_path,
            callback=engine.process_packet,
        )

    finally:
        engine.finish()


def run_live(interface, duration, output_path, packet_filter=None):
    """Extract features from live network traffic."""

    engine = FeatureEngine(output_path)

    try:
        capture_live(
            interface=interface,
            callback=engine.process_packet,
            duration=duration,
            packet_filter=packet_filter,
        )

    finally:
        engine.finish()


def build_parser():
    parser = argparse.ArgumentParser(
        description="NMT Network Flow Feature Extraction Engine"
    )

    parser.add_argument(
        "--mode",
        choices=["interfaces", "pcap", "live"],
        required=True,
        help="Select interface listing, PCAP processing or live capture",
    )

    parser.add_argument(
        "--input",
        type=str,
        help="Input PCAP or PCAPNG file",
    )

    parser.add_argument(
        "--interface",
        type=str,
        help="Network interface for live capture",
    )

    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Live capture duration in seconds (default: 60)",
    )

    parser.add_argument(
        "--output",
        type=str,
        default=str(DEFAULT_OUTPUT),
        help="Output CSV file path",
    )

    parser.add_argument(
        "--filter",
        type=str,
        default=None,
        help="Optional BPF capture filter, e.g. tcp or udp",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    output_path = Path(args.output)

    if args.mode == "interfaces":
        list_interfaces()
        return

    if args.mode == "pcap":
        if not args.input:
            parser.error("--input is required for PCAP mode")

        run_pcap(
            input_path=args.input,
            output_path=output_path,
        )

    elif args.mode == "live":
        if not args.interface:
            parser.error("--interface is required for live mode")

        if args.duration <= 0:
            parser.error("--duration must be greater than zero")

        run_live(
            interface=args.interface,
            duration=args.duration,
            output_path=output_path,
            packet_filter=args.filter,
        )


if __name__ == "__main__":
    main()
