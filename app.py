from fastapi import FastAPI, Request, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn
import requests
from bs4 import BeautifulSoup
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Make sure src is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from builder.builder import build_one
from builder.models import ProspectInput
from builder.batch import slugify

app = FastAPI(title="Website Builder Web Interface")

# Ensure static directory exists
os.makedirs(str(Path(__file__).resolve().parent / "static"), exist_ok=True)

# Mount static and dist directories
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")
app.mount("/dist", StaticFiles(directory=str(Path(__file__).resolve().parent / "dist")), name="dist")

class GenerateRequest(BaseModel):
    input_data: str # URL or text
    company_name: str = ""

def extract_text_from_url(url: str):
    try:
        # Add http if missing
        if not url.startswith("http"):
            url = "https://" + url
            
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract title
        title = soup.title.string if soup.title else ""
        
        # Remove scripts, styles
        for script in soup(["script", "style", "nav", "footer"]):
            script.decompose()
            
        text = soup.get_text(separator=' ', strip=True)
        return {"title": title, "text": text}
    except Exception as e:
        raise ValueError(f"Failed to fetch URL: {str(e)}")

def is_url(text: str) -> bool:
    try:
        result = urlparse(text)
        return all([result.scheme, result.netloc]) or (text.count('.') > 0 and ' ' not in text)
    except:
        return False

@app.post("/api/generate")
def generate_site(req: GenerateRequest):
    source_text = req.input_data
    company_name = req.company_name
    
    if is_url(req.input_data):
        try:
            extracted = extract_text_from_url(req.input_data)
            source_text = extracted["text"]
            if not company_name:
                company_name = extracted["title"].split('-')[0].split('|')[0].strip()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
            
    if not company_name:
        company_name = "Nouvelle Entreprise"
        
    slug = slugify(company_name)
    import time
    slug = f"{slug}-{int(time.time())}" # Ensure unique slug for web requests
    
    prospect = ProspectInput(
        slug=slug,
        company_name=company_name,
        source_text=source_text[:10000] # Limit size
    )
    
    try:
        # Build site
        result = build_one(prospect)
        
        if result.ok:
            return {
                "success": True, 
                "slug": slug, 
                "url": f"/dist/{slug}/index.html",
                "cost_usd": result.cost_usd
            }
        else:
            return {"success": False, "error": result.error}
            
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/")
def read_root():
    static_dir = Path(__file__).resolve().parent / "static"
    with open(static_dir / "index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
