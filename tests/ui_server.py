"""Start the API + built interface with sample data (used by ``npm run e2e``).

Usage: python tests/ui_server.py <work-folder> <port> <token>
"""

import os
import sys
from pathlib import Path

work, port, token = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
os.environ["OFFICEFLOW_HOME"] = str(work / "home")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402

from officeflow.server.app import create_app  # noqa: E402
from officeflow.services.settings import Settings  # noqa: E402
from tests.conftest import make_pdf, make_xlsx  # noqa: E402

data = work / "data"
for name, text in [("A/invoice.pdf", "Invoice 2024/01/005"), ("A/letter.pdf", "Nothing"),
                   ("B/note.pdf", "Ref 2024/01/005"), ("B/contract.pdf", "Contract 2024/02/123")]:
    make_pdf(data / "pdfs" / name, [text])
make_xlsx(data / "excel" / "clients.xlsx", [{"Nom": " Ali ", "Montant": 10}, {"Nom": "Sara", "Montant": 5}])
settings = Settings.load()
settings.output_dir, settings.last_input_dir = str(work / "out"), str(data / "pdfs")
settings.save()
uvicorn.run(create_app(token), host="127.0.0.1", port=port, log_level="warning")
