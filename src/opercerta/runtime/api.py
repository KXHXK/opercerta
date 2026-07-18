import os

import uvicorn

from opercerta.api.app import create_production_app
from opercerta.observability.logging import configure_json_logging


def main() -> None:
    configure_json_logging("opercerta-api")
    uvicorn.run(
        create_production_app(),
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        log_config=None,
    )


if __name__ == "__main__":
    main()
