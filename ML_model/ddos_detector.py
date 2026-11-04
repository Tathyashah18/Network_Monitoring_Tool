
import os
import joblib
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_PATH = os.path.join(
    BASE_DIR,
    "models",
    "nmt_xgboost_grouped_final.joblib"
)

# Load model once when the module is imported.
artifact = joblib.load(MODEL_PATH)

model = artifact["model"]
FEATURES = artifact["features"]
MEDIANS = pd.Series(artifact["medians"])
THRESHOLD = float(artifact["threshold"])


def predict_ddos(flow_data):
    """
    Input:
        Dictionary containing the 62 flow features.

    Output:
        Attack probability and classification.
    """

    if not isinstance(flow_data, dict):
        raise TypeError("flow_data must be a dictionary")

    missing = [
        feature for feature in FEATURES
        if feature not in flow_data
    ]

    if missing:
        raise ValueError(
            f"Missing model features: {missing}"
        )

    X = pd.DataFrame(
        [flow_data],
        columns=FEATURES
    )

    for feature in FEATURES:
        X[feature] = pd.to_numeric(
            X[feature],
            errors="coerce"
        )

    X.replace(
        [np.inf, -np.inf],
        np.nan,
        inplace=True
    )

    X = X.fillna(MEDIANS).fillna(0)

    probability = float(
        model.predict_proba(X)[0][1]
    )

    prediction = int(
        probability >= THRESHOLD
    )

    return {
        "attack_probability": probability,
        "prediction": prediction,
        "status": (
            "ATTACK" if prediction == 1
            else "BENIGN"
        ),
        "threshold": THRESHOLD
    }
