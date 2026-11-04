
import csv
from datetime import datetime, timezone
from pathlib import Path

from .config import CSV_COLUMNS, FEATURE_DIR
from .feature_extractor import extract_features


class FlowExporter:

    def __init__(self, output_path=None):

        self.output_path = Path(
            output_path
            if output_path
            else FEATURE_DIR / "nmt_flow_features.csv"
        )

        self.output_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        file_exists = (
            self.output_path.exists()
            and self.output_path.stat().st_size > 0
        )

        if file_exists:
            with open(
                self.output_path,
                mode="r",
                newline="",
                encoding="utf-8-sig"
            ) as existing_file:

                existing_header = next(
                    csv.reader(existing_file),
                    None
                )

            if existing_header != CSV_COLUMNS:
                raise ValueError(
                    "Existing CSV header does not match the "
                    "current feature schema. Use a different "
                    "output filename or resolve the schema mismatch."
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

        if not file_exists:
            self.writer.writeheader()
            self.file.flush()

        self.exported_count = 0

    def export_flow(self, flow):
        """Extract features and append one completed flow."""

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

        # Make the record visible in the CSV immediately.
        self.file.flush()

        self.exported_count += 1

        return row

    def export_flows(self, flows):
        """Export multiple flows."""

        exported = []

        for flow in flows:
            exported.append(
                self.export_flow(flow)
            )

        return exported

    def close(self):
        """Flush and safely close the CSV."""

        if not self.file.closed:
            self.file.flush()
            self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
