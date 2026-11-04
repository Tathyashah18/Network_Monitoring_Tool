
from scapy.all import IP, TCP, UDP, wrpcap
from pathlib import Path

packets = []

base_time = 1700000000.0

# TCP forward packets
for i in range(5):
    packet = (
        IP(src="192.168.1.10", dst="192.168.1.20")
        / TCP(sport=5000, dport=80, flags="PA")
        / ("TEST_PACKET_%d" % i)
    )
    packet.time = base_time + i * 0.1
    packets.append(packet)

# TCP backward packets
for i in range(3):
    packet = (
        IP(src="192.168.1.20", dst="192.168.1.10")
        / TCP(sport=80, dport=5000, flags="A")
        / ("RESPONSE_%d" % i)
    )
    packet.time = base_time + 0.55 + i * 0.1
    packets.append(packet)

# UDP packets
for i in range(4):
    packet = (
        IP(src="192.168.1.30", dst="192.168.1.40")
        / UDP(sport=6000, dport=53)
        / ("UDP_TEST_%d" % i)
    )
    packet.time = base_time + 1.0 + i * 0.2
    packets.append(packet)

output = Path(__file__).resolve().parent / "test_traffic.pcap"

wrpcap(str(output), packets)

print("Test PCAP created:", output)
print("Total packets:", len(packets))
