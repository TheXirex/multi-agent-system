"""
Main execution entrypoint for running the backend API service via `python -m backend`.
"""
import os
import uvicorn


def main() -> None:
    """
    Runs the AI FastAPI backend service using uvicorn on the configured host and port.
    """
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
