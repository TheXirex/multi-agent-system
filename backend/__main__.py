import os

from dotenv import load_dotenv
import uvicorn

load_dotenv()


def main() -> None:
    """Runs the FastAPI backend gateway service using Uvicorn."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
