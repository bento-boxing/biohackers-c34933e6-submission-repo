import os

from dotenv import load_dotenv

from pipeline.api import create_app

load_dotenv()
app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1", port=5000)
