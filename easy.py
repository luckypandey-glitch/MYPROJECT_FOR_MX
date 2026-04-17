from fastapi import FastAPI, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import requests
import dns.resolver
import socket
from urllib.parse import urlparse
from ipwhois import IPWhois
import io
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def clean_domain(domain):

    if not domain:
        return ""

    domain = str(domain).strip().lower()

    domain = re.sub(r"https?://", "", domain)
    domain = domain.replace("www.", "")

    return domain.split("/")[0]

def detect_column(df, names):

    for name in names:
        if name in df.columns:
            return name

    return None

def get_domain(company, api_key):

    if not company:
        return ""

    try:

        r = requests.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google",
                "q": f"{company} official website",
                "api_key": api_key
            },
            timeout=15
        )

        data = r.json()

        results = data.get("organic_results", [])

        if results:

            link = results[0].get("link", "")

            if link:
                domain = urlparse(link).netloc
                return domain.replace("www.", "")

    except:
        pass

    return ""

def get_company(domain, api_key):

    if not domain:
        return ""

    try:

        r = requests.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google",
                "q": f"site:{domain}",
                "api_key": api_key
            },
            timeout=15
        )

        data = r.json()

        if "knowledge_graph" in data:
            name = data["knowledge_graph"].get("title")
            if name:
                return name

        if "organic_results" in data:

            title = data["organic_results"][0].get("title", "")

            title = title.split("|")[0]
            title = title.split("-")[0]

            return title.strip()

    except:
        pass

    return ""

def lookup_mx(domain):
    if not domain:
        return "", "", "", ""
 
    try:
        answers = dns.resolver.resolve(domain, "MX")
        mx = str(answers[0].exchange).rstrip(".")
 
        try:
            ip = socket.gethostbyname(mx)
        except:
            ip = ""
 
        try:
            host = socket.gethostbyaddr(ip)[0] if ip else ""
        except:
            host = ""
 
        try:
            if ip:
                obj = IPWhois(ip)
                whois = obj.lookup_rdap()
                org = whois.get("network", {}).get("name", "")
            else:
                org = ""
        except:
            org = ""
 
        return mx, ip, host, org
 
    except:
        return "No MX", "", "", ""

def remove_duplicates(df):

    df["Domain"] = df["Domain"].astype(str).str.lower().str.strip()
    df["Company Name"] = df["Company Name"].astype(str).str.lower().str.strip()

    seen_domains = set()
    seen_companies = set()

    clean_rows = []

    for _, row in df.iterrows():

        domain = row["Domain"]
        company = row["Company Name"]

        if domain and domain in seen_domains:
            continue

        if company and company in seen_companies:
            continue

        if domain:
            seen_domains.add(domain)

        if company:
            seen_companies.add(company)

        clean_rows.append(row)

    return pd.DataFrame(clean_rows)

@app.post("/process/")
async def process_file(
    file: UploadFile,
    mode: str = Form(...),
    api_key: str = Form("")
):

    contents = await file.read()

    df = pd.read_csv(io.BytesIO(contents), encoding="utf-8", on_bad_lines="skip")

    domain_col = detect_column(df, ["Domain","domain","Website"])
    company_col = detect_column(df, ["Company Name","Company","company"])

    if domain_col:
        df.rename(columns={domain_col:"Domain"}, inplace=True)
    else:
        df["Domain"] = ""

    if company_col:
        df.rename(columns={company_col:"Company Name"}, inplace=True)
    else:
        df["Company Name"] = ""

    results = []

    for _, row in df.iterrows():

        company = str(row["Company Name"]).strip()
        domain = clean_domain(row["Domain"])

        mx = ip = host = org = ""

        if mode == "find_mx":

            if domain:
                mx, ip, host, org = lookup_mx(domain)

        elif mode == "find_domain":

            domain = get_domain(company, api_key)

        elif mode == "find_company":

            if domain:
                company = get_company(domain, api_key)

        elif mode == "mx_domain":

            domain = get_domain(company, api_key)

            if domain:
                mx, ip, host, org = lookup_mx(domain)

        elif mode == "company_mx":

            if domain:
                company = get_company(domain, api_key)
                mx, ip, host, org = lookup_mx(domain)

        results.append({
            "Company Name": company,
            "Domain": domain,
            "MX Record": mx,
            "IP": ip,
            "Host": host,
            "Organization": org
        })

    result_df = pd.DataFrame(results)

    if mode == "remove_duplicate":
        result_df = remove_duplicates(result_df)

    return {"data": result_df.to_dict(orient="records")}
