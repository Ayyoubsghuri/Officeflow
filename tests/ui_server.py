"""Start the API + built interface with sample data (used by ``npm run e2e``).

Usage: python tests/ui_server.py <work-folder> <port> <token>
"""

import os
import time
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
app = create_app(token)
if os.environ.get("OFFICEFLOW_FAKE_AI"):
    # Stand-in for Claude so the interface can be tested without an API key.
    from officeflow.ai import assistant as ai
    from tests.test_ai import GOOD_PLUGIN, FakeClient, workflow_answer

    def factory(provider, key, model):
        fake = FakeClient(
            workflow_answer([("pdf.organize", {"patterns": r"\b\d{4}/\d{2}/\d{3}\b"}), ("pdf.search", {"find": "Total"})],
                            missing=[{"name": "OCR", "description": "Read scanned PDFs.", "reads": [".pdf"],
                                      "writes": [".pdf"]}]),
            ai.PluginAnswer(file_name="count_pages.py", explanation="Counts the pages of each PDF.", code=GOOD_PLUGIN))

        class Picker(ai.Assistant):
            def design_workflow(self, request):
                time.sleep(1.5)              # long enough to leave the page while it works
                return super().design_workflow(request)

            def create_plugin(self, request):
                fake.answers.pop(0)          # skip the workflow answer
                return super().create_plugin(request)

        return Picker(key or "fake", model, client=fake, provider=provider)

    app.state.assistant_factory = factory
    app.state.list_models = lambda provider, key: ai.list_provider_models(provider, key, client=FakeClient())
uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
