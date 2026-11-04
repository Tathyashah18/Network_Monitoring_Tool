from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

CAPTURE_DIR = BASE_DIR / "captures"
FEATURE_DIR = BASE_DIR / "extracted_features"
MODEL_DIR = BASE_DIR / "models"

DEFAULT_OUTPUT = FEATURE_DIR / "nmt_flow_features.csv"

FLOW_TIMEOUT_SECONDS = 5.0
ACTIVE_TIMEOUT_SECONDS = 2.0
SUBFLOW_INTERVAL_SECONDS = 1.0

SUPPORTED_PROTOCOLS = {
    1: "ICMP",
    6: "TCP",
    17: "UDP",
    58: "ICMPv6",
}

METADATA_COLUMNS = [
    "Flow Start UTC",
    "Protocol",
]

FEATURE_COLUMNS = [
    "Flow Duration",
    "Total Fwd Packets",
    "Total Backward Packets",
    "Total Length of Fwd Packets",
    "Total Length of Bwd Packets",
    "Flow Bytes/s",
    "Flow Packets/s",
    "Fwd Packet Length Max",
    "Fwd Packet Length Min",
    "Fwd Packet Length Mean",
    "Bwd Packet Length Max",
    "Bwd Packet Length Mean",
    "Packet Length Mean",
    "SYN Flag Count",
    "ACK Flag Count",
    "RST Flag Count",
    "FIN Flag Count",
    "PSH Flag Count",
    "URG Flag Count",
    "Flow IAT Mean",
    "Flow IAT Std",
    "Flow IAT Max",
    "Flow IAT Min",
    "Fwd IAT Mean",
    "Bwd IAT Mean",
    "Down/Up Ratio",
    "Average Packet Size",
    "Subflow Fwd Packets",
    "Subflow Bwd Packets",
    "Active Mean",
]

CSV_COLUMNS = METADATA_COLUMNS + FEATURE_COLUMNS