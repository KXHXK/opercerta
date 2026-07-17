import os

import uvicorn

from opercerta.api.app import create_production_app


def main() -> None:
    uvicorn.run(
        create_production_app(),
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
    )


if __name__ == "__main__":
    main()
