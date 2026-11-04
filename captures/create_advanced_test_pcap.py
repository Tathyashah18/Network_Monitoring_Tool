
from scapy.all import Ether, IP, TCP, UDP, Raw, wrpcap
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent / "advanced_test_traffic.pcap"

BASE_TIME = 1700000000.0

packets = []


def add_tcp(src, dst, sport, dport, flags, size, timestamp):
    packet = (
        Ether()
        / IP(src=src, dst=dst)
        / TCP(sport=sport, dport=dport, flags=flags)
    )

    header_size = len(packet)
    if size > header_size:
        packet = packet / Raw(b"X" * (size - header_size))

    packet.time = timestamp
    packets.append(packet)


def add_udp(src, dst, sport, dport, size, timestamp):
    packet = (
        Ether()
        / IP(src=src, dst=dst)
        / UDP(sport=sport, dport=dport)
    )

    header_size = len(packet)
    if size > header_size:
        packet = packet / Raw(b"U" * (size - header_size))

    packet.time = timestamp
    packets.append(packet)


# TCP flow: SYN, SYN-ACK, ACK, data, reverse data, FIN and RST.
tcp_src = "192.168.10.10"
tcp_dst = "192.168.10.20"

tcp_events = [
    (0.00, tcp_src, tcp_dst, 5000, 80, "S", 60),
    (0.05, tcp_dst, tcp_src, 80, 5000, "SA", 60),
    (0.10, tcp_src, tcp_dst, 5000, 80, "A", 54),
    (0.20, tcp_src, tcp_dst, 5000, 80, "PA", 150),
    (0.30, tcp_dst, tcp_src, 80, 5000, "A", 100),
    (0.40, tcp_src, tcp_dst, 5000, 80, "PA", 250),
    (0.50, tcp_dst, tcp_src, 80, 5000, "PA", 200),

    # Idle gap greater than ACTIVE_TIMEOUT_SECONDS.
    (3.50, tcp_src, tcp_dst, 5000, 80, "A", 54),
    (3.60, tcp_src, tcp_dst, 5000, 80, "FA", 54),
    (3.70, tcp_dst, tcp_src, 80, 5000, "FA", 54),
]

for offset, src, dst, sport, dport, flags, size in tcp_events:
    add_tcp(
        src, dst, sport, dport,
        flags, size, BASE_TIME + offset
    )


# Separate TCP flow containing a reset.
add_tcp(
    "192.168.10.30", "192.168.10.40",
    6000, 443, "RA", 60, BASE_TIME + 4.0
)


# UDP flow with different packet sizes and intervals.
udp_src = "192.168.10.50"
udp_dst = "192.168.10.60"

udp_events = [
    (0.00, 64),
    (0.10, 128),
    (0.20, 256),
    (1.20, 512),
    (1.30, 100),
    (3.50, 200),
]

for offset, size in udp_events:
    add_udp(
        udp_src, udp_dst,
        7000, 53,
        size, BASE_TIME + offset
    )


# Sort packets chronologically before writing.
packets.sort(key=lambda packet: float(packet.time))

wrpcap(str(OUTPUT), packets)

print("Advanced PCAP generated successfully.")
print("Output:", OUTPUT)
print("Total packets:", len(packets))
