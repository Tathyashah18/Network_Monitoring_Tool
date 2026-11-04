
import csv
from datetime import datetime, timezone
from pathlib import Path

from .config import CSV_COLUMNS, FEATURE_DIR
from .feature_extractor import extract_features


class FlowExporter:

    def __init__(self, output_path=None):
        self.output_path = Path(
            output_path if output_path else
            FEATURE_DIR / "nmt_flow_features.csv"
        )

        self.output_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        self.file_exists = (
            self.output_path.exists()
            and self.output_path.stat().st_size > 0
        )

        self.file = open(
            self.output_path,
            mode="a",
            newline="",
            encoding="utf-8"
        )

        self.writer = csv.DictWriter(
            self.file,
            fieldnames=CSV_COLUMNS
        )

        if not self.file_exists:
            self.writer.writeheader()
            self.file.flush()

    def export_flow(self, flow):
        """Extract features and append one flow to the CSV."""

        features = extract_features(flow)

        row = {
            "Flow Start UTC": datetime.fromtimestamp(
                flow.start_time,
                tz=timezone.utc
            ).isoformat(),

            "Protocol": flow.protocol,
        }

        row.update(features)

        self.writer.writerow(row)
        self.file.flush()

        return row

    def export_flows(self, flows):
        """Export multiple flows."""

        exported = []

        for flow in flows:
            exported.append(self.export_flow(flow))

        return exported

    def close(self):
        """Close the CSV file safely."""

        if not self.file.closed:
            self.file.flush()
            self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
