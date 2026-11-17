import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local intake demonstration service")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run("intake_draft.api:app", host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
