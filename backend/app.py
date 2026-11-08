import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from pipeline.api import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1", port=5000)
