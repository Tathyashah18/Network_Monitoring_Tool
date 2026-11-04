from dataclasses import dataclass, field
import ipaddress

from scapy.all import IP, IPv6, TCP, UDP, ICMP


@dataclass
class Flow:
    flow_id: tuple
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: int
    start_time: float
    last_time: float

    packet_lengths: list = field(default_factory=list)
    timestamps: list = field(default_factory=list)

    fwd_lengths: list = field(default_factory=list)
    bwd_lengths: list = field(default_factory=list)

    fwd_timestamps: list = field(default_factory=list)
    bwd_timestamps: list = field(default_factory=list)

    syn_count: int = 0
    ack_count: int = 0
    rst_count: int = 0
    fin_count: int = 0
    psh_count: int = 0
    urg_count: int = 0

    def add_packet(self, timestamp, length, direction, tcp_flags=None):
        self.last_time = timestamp

        self.packet_lengths.append(length)
        self.timestamps.append(timestamp)

        if direction == 0:
            self.fwd_lengths.append(length)
            self.fwd_timestamps.append(timestamp)
        else:
            self.bwd_lengths.append(length)
            self.bwd_timestamps.append(timestamp)

        if tcp_flags is not None:
            self.syn_count += int(bool(tcp_flags & 0x02))
            self.ack_count += int(bool(tcp_flags & 0x10))
            self.rst_count += int(bool(tcp_flags & 0x04))
            self.fin_count += int(bool(tcp_flags & 0x01))
            self.psh_count += int(bool(tcp_flags & 0x08))
            self.urg_count += int(bool(tcp_flags & 0x20))

    @property
    def total_packets(self):
        return len(self.packet_lengths)

    @property
    def duration(self):
        return max(0.0, self.last_time - self.start_time)


class FlowManager:

    def __init__(self, flow_timeout=5.0):
        self.flows = {}
        self.flow_timeout = float(flow_timeout)

    @staticmethod
    def _packet_details(packet):
        if IP in packet:
            ip_layer = packet[IP]
            src_ip = ip_layer.src
            dst_ip = ip_layer.dst
            protocol = int(ip_layer.proto)
            length = int(ip_layer.len or len(ip_layer))

        elif IPv6 in packet:
            ip_layer = packet[IPv6]
            src_ip = ip_layer.src
            dst_ip = ip_layer.dst
            protocol = int(ip_layer.nh)
            length = int(ip_layer.plen) + 40

        else:
            return None

        src_port = 0
        dst_port = 0
        tcp_flags = None

        if TCP in packet:
            transport = packet[TCP]
            src_port = int(transport.sport)
            dst_port = int(transport.dport)
            protocol = 6
            tcp_flags = int(transport.flags)

        elif UDP in packet:
            transport = packet[UDP]
            src_port = int(transport.sport)
            dst_port = int(transport.dport)
            protocol = 17

        elif ICMP in packet:
            protocol = 1

        return {
            "src_ip": str(ipaddress.ip_address(src_ip)),
            "dst_ip": str(ipaddress.ip_address(dst_ip)),
            "src_port": src_port,
            "dst_port": dst_port,
            "protocol": protocol,
            "length": length,
            "tcp_flags": tcp_flags,
            "timestamp": float(packet.time),
        }

    @staticmethod
    def _make_flow_key(details):
        endpoint_a = (
            details["src_ip"],
            details["src_port"],
        )

        endpoint_b = (
            details["dst_ip"],
            details["dst_port"],
        )

        endpoints = tuple(sorted((endpoint_a, endpoint_b)))

        return details["protocol"], endpoints

    def process_packet(self, packet):
        details = self._packet_details(packet)

        if details is None:
            return None

        timestamp = details["timestamp"]
        key = self._make_flow_key(details)

        flow = self.flows.get(key)

        # A flow starts a new window after an idle timeout.
        if flow is not None:
            if timestamp - flow.last_time > self.flow_timeout:
                del self.flows[key]
                flow = None

        if flow is None:
            flow = Flow(
                flow_id=key,
                src_ip=details["src_ip"],
                dst_ip=details["dst_ip"],
                src_port=details["src_port"],
                dst_port=details["dst_port"],
                protocol=details["protocol"],
                start_time=timestamp,
                last_time=timestamp,
            )
            self.flows[key] = flow

        direction = 0 if (
            details["src_ip"] == flow.src_ip
            and details["src_port"] == flow.src_port
        ) else 1

        flow.add_packet(
            timestamp=timestamp,
            length=details["length"],
            direction=direction,
            tcp_flags=details["tcp_flags"],
        )

        return flow

    def get_expired_flows(self, current_time):
        expired = []

        for key, flow in list(self.flows.items()):
            if current_time - flow.last_time > self.flow_timeout:
                expired.append(flow)
                del self.flows[key]

        return expired

    def flush_all(self):
        remaining = list(self.flows.values())
        self.flows.clear()
        return remaining

    def active_flow_count(self):
        return len(self.flows)