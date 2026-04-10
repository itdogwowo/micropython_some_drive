import json


def load_config():
    candidates = [
        "dp_config.json",
        "./dp_config.json",
        "jpeg/dp_config.json",
        "./jpeg/dp_config.json",
        "/jpeg/dp_config.json",
    ]
    last_err = None
    for p in candidates:
        try:
            with open(p, "r") as f:
                return json.load(f)
        except Exception as e:
            last_err = e
    raise last_err
