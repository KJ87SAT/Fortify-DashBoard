import os
import json
import requests
from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeSerializer, BadSignature
from config import *

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

serializer = URLSafeSerializer(SECRET_KEY)

DATA_PATH = "data/guilds"
os.makedirs(DATA_PATH, exist_ok=True)


# -----------------------
# Utility
# -----------------------

def get_guilds(token):
    r = requests.get(
        f"{API_BASE}/users/@me/guilds",
        headers={"Authorization": f"Bearer {token}"}
    )
    if r.status_code != 200:
        return []
    return r.json()


def bot_in_guild(guild_id):
    r = requests.get(
        f"{API_BASE}/guilds/{guild_id}",
        headers={"Authorization": f"Bot {BOT_TOKEN}"}
    )
    return r.status_code == 200


def get_guild_file(guild_id):
    path = f"{DATA_PATH}/{guild_id}.json"

    if not os.path.exists(path):
        default = {
            "spam_protection": {
                "enabled": False,
                "limit": 5,
                "whitelist_roles": [],
                "whitelist_users": []
            },
            "join_raid": {
                "enabled": False
            },
            "backup": {
                "categories": 0,
                "channels": 0,
                "roles": 0,
                "last_backup": "None"
            }
        }
        with open(path, "w") as f:
            json.dump(default, f, indent=4)

    with open(path, "r") as f:
        return json.load(f)


def save_guild_file(guild_id, data):
    with open(f"{DATA_PATH}/{guild_id}.json", "w") as f:
        json.dump(data, f, indent=4)


# -----------------------
# Routes
# -----------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/login")
async def login():
    return RedirectResponse(
        f"https://discord.com/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope=identify%20guilds"
    )


@app.get("/callback")
async def callback(code: str):
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post(f"{API_BASE}/oauth2/token", data=data, headers=headers)

    token = r.json().get("access_token")
    if not token:
        return HTMLResponse("OAuth Failed", status_code=400)

    response = RedirectResponse("/servers", status_code=302)

    # 🔥 Codespaces対応Cookie設定
    response.set_cookie(
        key="session",
        value=serializer.dumps(token),
        httponly=True,
        secure=True,
        samesite="none"
    )

    return response


@app.get("/servers", response_class=HTMLResponse)
async def servers(request: Request):
    token_cookie = request.cookies.get("session")
    if not token_cookie:
        return RedirectResponse("/", status_code=302)

    try:
        token = serializer.loads(token_cookie)
    except BadSignature:
        return RedirectResponse("/", status_code=302)

    guilds = get_guilds(token)

    admin_guilds = [
        g for g in guilds
        if (int(g["permissions"]) & 0x8) == 0x8
        and bot_in_guild(g["id"])
    ]


    return templates.TemplateResponse("servers.html", {
        "request": request,
        "guilds": admin_guilds,
        "bot_check": bot_in_guild
    })


@app.get("/dashboard/{guild_id}", response_class=HTMLResponse)
async def dashboard(request: Request, guild_id: str):
    if not bot_in_guild(guild_id):
        return HTMLResponse("Bot is not in this server.", status_code=403)

    data = get_guild_file(guild_id)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "guild_id": guild_id,
        "data": data
    })


@app.post("/dashboard/{guild_id}")
async def save_settings(
        guild_id: str,
        spam_enabled: str = Form(None),
        join_enabled: str = Form(None)
):
    data = get_guild_file(guild_id)

    data["spam_protection"]["enabled"] = spam_enabled == "on"
    data["join_raid"]["enabled"] = join_enabled == "on"

    save_guild_file(guild_id, data)

    return RedirectResponse(f"/dashboard/{guild_id}", status_code=303)


@app.get("/logout")
async def logout():
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie("session")
    return response
