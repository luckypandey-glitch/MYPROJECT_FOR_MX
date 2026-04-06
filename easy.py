from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import requests
import dns.resolver
import socket
from urllib.parse import urlparse
from ipwhois import IPWhois
import io

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_domain(company, api_key):

    try:
        r = requests.get(
            "https://serpapi.com/search.json",
            params={
                "q": f"{company} official website",
                "engine": "google",
                "api_key": api_key
            },
            timeout=10
        )

        data = r.json()
        results = data.get("organic_results", [])

        if results:
            link = results[0].get("link")
            return urlparse(link).netloc.replace("www.", "")

    except Exception as e:
        print("Domain error:", e)

    return ""

def lookup_mx(domain):

    try:
        answers = dns.resolver.resolve(domain, "MX")
        mx = str(answers[0].exchange).rstrip(".")

        ip = socket.gethostbyname(mx)

        try:
            host = socket.gethostbyaddr(ip)[0]
        except:
            host = "Unknown"

        try:
            obj = IPWhois(ip)
            whois = obj.lookup_rdap()
            org = whois.get("network", {}).get("name", "Unknown Org")
        except:
            org = "Unknown Org"

        return mx, ip, host, org

    except Exception:
        return "No MX", "", "", ""


@app.post("/process/")
async def process_file(
    file: UploadFile,
    mode: str = Form(...),
    api_key: str = Form("")
):

    contents = await file.read()

    df = pd.read_csv(io.StringIO(contents.decode()))

    results = []

    for _, row in df.iterrows():

        company = str(row.get("Company Name", "")).strip()
        domain = str(row.get("Domain", "")).strip()

        mx = ip = host = org = ""

        if mode == "domain_only":
            domain = get_domain(company, api_key)

        elif mode == "both":
            domain = get_domain(company, api_key)
            if domain:
                mx, ip, host, org = lookup_mx(domain)

        elif mode == "mx_only":
            if domain:
                mx, ip, host, org = lookup_mx(domain)

        results.append({
            "Company Name": company,
            "Domain": domain,
            "MX Record": mx,
            "IP": ip,
            "Host": host,
            "Org": org
        })

    return {"data": results}


