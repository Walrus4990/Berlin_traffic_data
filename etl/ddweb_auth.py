# AUTHENTICATE WITH DDWEB
import requests
from datetime import datetime
import os
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import time
import random

load_dotenv()       #loads environmental variables from .env

# ------- create class to store login and authentication info throughout session

class DDWebAuth:
    BASE_URL = "https://ddweb.topo-web.com"
    LOGIN_URL = f"{BASE_URL}/Account/Login"

    def __init__(self):
        self.email = os.getenv("DDWEB_EMAIL") #fetch username from .env
        self.password = os.getenv("DDWEB_PASSWORD")
        self.session = requests.Session()           #temprary memory that carries the three required cookies throuout the session
        self.last_authenticated_at = None           #these will be filled by following functions
        self.cookie_csrf = None                     #not used delete if not required at all
        self.cookie_session_id = None
        self.cookie_auth = None

        self.session.headers.update({               #send info on the computer making the request to show it s not a bot
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:149.0) Gecko/20100101 Firefox/149.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Connection": "keep-alive",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Dest": "script",
            "Sec-GPC": "1"
        })


    # ------- call login function and get the three required cookies and store them

    def authenticate(self):
        payload = {                       # dictionary used for authentification
            "Email": self.email,
            "Password": self.password
        }
        response = self.session.post(self.LOGIN_URL, data=payload)
        response.raise_for_status()

        if "/Account/Login" in response.url:
            raise ValueError("Authentication failed — still on login page. Check credentials.")

        self.cookie_session_id = self.session.cookies.get("ASP.NET_SessionId")
        self.cookie_auth = self.session.cookies.get("AspNet.DDWebFrontend")

        if not all([self.cookie_session_id, self.cookie_auth]):
            raise ValueError("Authentication appeared to succeed but one or more cookies are missing.")

        self.last_authenticated_at = datetime.now()


    # ------- check we are still logged in by hitting the Dashboard and seeing if we get it or back to login page
    # Calls authenticate in case we are back at login.
    # Adding random retry interval to mimic human behaviour

    def ensure_authenticated(self, max_attempts=3):
        for attempt in range(max_attempts):
            response = self.session.get(f"{self.BASE_URL}/Dashboard")
            if "/Account/Login" not in response.url:
                return
            self.authenticate()
            if attempt < max_attempts - 1:
                wait = random.uniform(3, 7)
                time.sleep(wait)

        raise RuntimeError("Could not authenticate after 3 attempts. Portal may be down.")
