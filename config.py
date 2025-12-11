import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    APP_KEY = os.getenv("APP_KEY")
    APP_SECRET = os.getenv("APP_SECRET")
    CANO = os.getenv("CANO")
    ACNT_PRDT_CD = os.getenv("ACNT_PRDT_CD")
    URL_BASE = os.getenv("URL_BASE", "https://openapi.koreainvestment.com:9443")

    @classmethod
    def validate(cls):
        missing = []
        if not cls.APP_KEY: missing.append("APP_KEY")
        if not cls.APP_SECRET: missing.append("APP_SECRET")
        if not cls.CANO: missing.append("CANO")
        
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
