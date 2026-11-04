
import math
import statistics

from .config import (
    FEATURE_COLUMNS,
    ACTIVE_TIMEOUT_SECONDS,
    SUBFLOW_INTERVAL_SECONDS,
)


def safe_mean(values):
    return statistics.mean(values) if values else 0.0


def safe_std(values):
    return statistics.pstdev(values) if len(values) > 1 else 0.0


def safe_max(values):
    return max(values) if values else 0.0


def safe_min(values):
    return min(values) if values else 0.0


def calculate_iat(timestamps):
    """Calculate inter-arrival times in microseconds."""

    ordered = sorted(timestamps)

    return [
        (ordered[i] - ordered[i - 1]) * 1_000_000
        for i in range(1, len(ordered))
    ]


def calculate_active_periods(timestamps):
    """Divide timestamps into active periods using the configured timeout."""

    if not timestamps:
        return []

    ordered = sorted(timestamps)

    periods = []
    period_start = ordered[0]
    previous = ordered[0]

    for timestamp in ordered[1:]:

        gap = timestamp - previous

        if gap > ACTIVE_TIMEOUT_SECONDS:

            periods.append(
                (previous - period_start) * 1_000_000
            )

            period_start = timestamp

        previous = timestamp

    periods.append(
        (previous - period_start) * 1_000_000
    )

    return periods


def calculate_subflow_packets(timestamps):
    """
    Calculate average packets per occupied fixed-width interval.

    This remains an NMT-specific approximation.
    """

    if not timestamps:
        return 0.0

    if SUBFLOW_INTERVAL_SECONDS <= 0:
        raise ValueError(
            "SUBFLOW_INTERVAL_SECONDS must be greater than zero."
        )

    ordered = sorted(timestamps)

    interval_counts = {}

    for timestamp in ordered:

        interval = int(
            (timestamp - ordered[0])
            // SUBFLOW_INTERVAL_SECONDS
        )

        interval_counts[interval] = (
            interval_counts.get(interval, 0) + 1
        )

    return safe_mean(
        list(interval_counts.values())
    )


def calculate_average_packet_size(packet_lengths):
    """Calculate average packet size using the existing NMT formula."""

    if not packet_lengths:
        return 0.0

    return (
        sum(packet_lengths) + len(packet_lengths)
    ) / len(packet_lengths)


def calculate_active_mean(timestamps):
    """Calculate the mean duration of active periods."""

    active_periods = calculate_active_periods(
        timestamps
    )

    return safe_mean(active_periods)


def extract_features(flow):
    """Extract all configured numerical flow features."""

    fwd = flow.fwd_lengths
    bwd = flow.bwd_lengths

    all_lengths = flow.packet_lengths

    fwd_timestamps = flow.fwd_timestamps
    bwd_timestamps = flow.bwd_timestamps

    duration_seconds = max(
        0.0,
        flow.duration
    )

    duration_microseconds = (
        duration_seconds * 1_000_000
    )

    total_bytes = sum(all_lengths)
    total_packets = len(all_lengths)

    flow_bytes_per_second = (
        total_bytes / duration_seconds
        if duration_seconds > 0
        else 0.0
    )

    flow_packets_per_second = (
        total_packets / duration_seconds
        if duration_seconds > 0
        else 0.0
    )

    flow_iat = calculate_iat(
        flow.timestamps
    )

    fwd_iat = calculate_iat(
        fwd_timestamps
    )

    bwd_iat = calculate_iat(
        bwd_timestamps
    )

    down_up_ratio = (
        len(bwd) / len(fwd)
        if len(fwd) > 0
        else 0.0
    )

    features = {

        "Flow Duration": duration_microseconds,

        "Total Fwd Packets": len(fwd),

        "Total Backward Packets": len(bwd),

        "Total Length of Fwd Packets": sum(fwd),

        "Total Length of Bwd Packets": sum(bwd),

        "Flow Bytes/s": flow_bytes_per_second,

        "Flow Packets/s": flow_packets_per_second,

        "Fwd Packet Length Max": safe_max(fwd),

        "Fwd Packet Length Min": safe_min(fwd),

        "Fwd Packet Length Mean": safe_mean(fwd),

        "Bwd Packet Length Max": safe_max(bwd),

        "Bwd Packet Length Mean": safe_mean(bwd),

        "Packet Length Mean": safe_mean(all_lengths),

        "SYN Flag Count": flow.syn_count,

        "ACK Flag Count": flow.ack_count,

        "RST Flag Count": flow.rst_count,

        "FIN Flag Count": flow.fin_count,

        "PSH Flag Count": flow.psh_count,

        "URG Flag Count": flow.urg_count,

        "Flow IAT Mean": safe_mean(flow_iat),

        "Flow IAT Std": safe_std(flow_iat),

        "Flow IAT Max": safe_max(flow_iat),

        "Flow IAT Min": safe_min(flow_iat),

        "Fwd IAT Mean": safe_mean(fwd_iat),

        "Bwd IAT Mean": safe_mean(bwd_iat),

        "Down/Up Ratio": down_up_ratio,

        "Average Packet Size": calculate_average_packet_size(
            all_lengths
        ),

        "Subflow Fwd Packets": calculate_subflow_packets(
            fwd_timestamps
        ),

        "Subflow Bwd Packets": calculate_subflow_packets(
            bwd_timestamps
        ),

        "Active Mean": calculate_active_mean(
            flow.timestamps
        ),
    }

    missing_features = (
        set(FEATURE_COLUMNS) - set(features)
    )

    if missing_features:
        raise ValueError(
            f"Missing feature calculations: {sorted(missing_features)}"
        )

    ordered_features = {
        column: float(features[column])
        for column in FEATURE_COLUMNS
    }

    for name, value in ordered_features.items():

        if not math.isfinite(value):
            ordered_features[name] = 0.0

    return ordered_features
