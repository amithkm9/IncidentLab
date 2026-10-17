from __future__ import annotations

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the IncidentLab local demo.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--data-dir", default="runtime")
    args = parser.parse_args()
    os.environ["INCIDENTLAB_DATA_DIR"] = args.data_dir
    uvicorn.run("incidentlab.api:create_app", factory=True, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
