import os
from dotenv import load_dotenv

# Cargar .env explícitamente desde la ruta del proyecto
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")

    SQLALCHEMY_DATABASE_URI = (
        f"postgresql://{os.getenv('DATABASE_USER')}:{os.getenv('DATABASE_PASSWORD')}"
        f"@{os.getenv('DATABASE_HOST')}:{os.getenv('DATABASE_PORT')}/"
        f"{os.getenv('DATABASE_NAME')}"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    GALAXY_URL = os.getenv("GALAXY_URL")
    GALAXY_API_KEY = os.getenv("GALAXY_API_KEY")
