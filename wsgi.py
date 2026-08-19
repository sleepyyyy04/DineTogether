"""Entry point: `flask --app wsgi run --debug` or `python wsgi.py`."""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
