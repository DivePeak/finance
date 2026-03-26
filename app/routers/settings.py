from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import configparser
import os

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"))

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.cfg')

@router.get("/", response_class=HTMLResponse)
async def get_settings(request: Request):
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_PATH):
        config.read(CONFIG_PATH)
    
    stale_time = config.get('cache', 'stale_time_seconds', fallback='3600')
    
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "stale_time": stale_time
    })

@router.post("/", response_class=HTMLResponse)
async def update_settings(request: Request, stale_time: str = Form(...)):
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_PATH):
        config.read(CONFIG_PATH)
    
    if not config.has_section('cache'):
        config.add_section('cache')
    
    config.set('cache', 'stale_time_seconds', stale_time)
    
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)
    
    return RedirectResponse(url="/settings", status_code=303)
