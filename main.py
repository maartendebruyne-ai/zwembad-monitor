#!/usr/bin/env python3
"""
Zwembad Monitor - Blueriiot + Email Rapportage
Voor Render.com - draait als webservice met APScheduler
"""

import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask

app = Flask(__name__)

# ============================================================
# CONFIGURATIE
# ============================================================
BLUERIIOT_EMAIL    = "Info@studiogigant.be"
BLUERIIOT_PASSWORD = "1302mAd1024"

GMAIL_ADRES        = "maartendebruyne@gmail.com"
GMAIL_APP_PASS     = "nmdv kwsq sign njpg"

ONTVANGERS         = ["maartendebruyne@gmail.com", "maartenenmelissa@gmail.com"]

# ============================================================
# NORMEN
# ============================================================
NORMEN = {
    "ph": {
        "label": "pH",
        "ideaal": (7.2, 7.6),
        "kritiek_laag": 6.8,
        "kritiek_hoog": 7.8,
        "eenheid": "",
        "actie_laag": "Voeg pH-verhogend middel (pH+) toe aan het water.",
        "actie_hoog": "Voeg pH-verlagend middel (pH-) toe aan het water.",
    },
    "orp": {
        "label": "ORP (desinfectie)",
        "ideaal": (650, 750),
        "kritiek_laag": 600,
        "kritiek_hoog": 800,
        "eenheid": " mV",
        "actie_laag": "Voeg chloor of desinfectiemiddel toe. Controleer filtratie.",
        "actie_hoog": "Verlaag de chloorproductie of pas de dosering aan.",
    },
    "temperature": {
        "label": "Temperatuur",
        "ideaal": (22, 30),
        "kritiek_laag": 15,
        "kritiek_hoog": 35,
        "eenheid": "°C",
        "actie_laag": "Temperatuur is erg laag — controleer verwarming.",
        "actie_hoog": "Temperatuur is erg hoog — risico op algengroei, verhoog filtratie.",
    },
    "conductivity": {
        "label": "Conductiviteit",
        "ideaal": (400, 1200),
        "kritiek_laag": 200,
        "kritiek_hoog": 1500,
        "eenheid": " µS/cm",
        "actie_laag": "Mineraalgehalte laag — controleer waterbehandeling.",
        "actie_hoog": "Te veel mineralen — gedeeltelijk water verversen.",
    },
}

# ============================================================
# BLUERIIOT API
# ============================================================
BASE_URL = "https://api.blueriiot.com/api"

def blueriiot_login():
    session = requests.Session()
    resp = session.post(f"{BASE_URL}/user/login", json={
        "email": BLUERIIOT_EMAIL,
        "password": BLUERIIOT_PASSWORD
    })
    resp.raise_for_status()
    return session

def get_pool_data(session):
    pools_resp = session.get(f"{BASE_URL}/swimming_pool")
    pools_resp.raise_for_status()
    pools = pools_resp.json().get("data", [])
    if not pools:
        raise Exception("Geen zwembaden gevonden.")
    pool = pools[0]
    pool_id = pool["swimming_pool_id"]
    feed_resp = session.get(f"{BASE_URL}/swimming_pool/{pool_id}/blue/last_feed")
    feed_resp.raise_for_status()
    feed = feed_resp.json().get("data", {})
    return pool, feed

# ============================================================
# ANALYSE
# ============================================================
def analyseer(feed):
    resultaten = []
    kritiek = False
    for sleutel, norm in NORMEN.items():
        waarde = feed.get(sleutel)
        if waarde is None:
            continue
        laag, hoog = norm["ideaal"]
        status = "✅ OK"
        actie = ""
        if waarde < norm["kritiek_laag"] or waarde > norm["kritiek_hoog"]:
            status = "🚨 KRITIEK"
            kritiek = True
            actie = norm["actie_laag"] if waarde < norm["kritiek_laag"] else norm["actie_hoog"]
        elif waarde < laag:
            status = "⚠️ Te laag"
            actie = norm["actie_laag"]
        elif waarde > hoog:
            status = "⚠️ Te hoog"
            actie = norm["actie_hoog"]
        resultaten.append({
            "label": norm["label"],
            "waarde": waarde,
            "eenheid": norm["eenheid"],
            "ideaal": f"{laag}–{hoog}{norm['eenheid']}",
            "status": status,
            "actie": actie,
        })
    return resultaten, kritiek

# ============================================================
# EMAIL
# ============================================================
def stuur_email(onderwerp, html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = onderwerp
    msg["From"]    = GMAIL_ADRES
    msg["To"]      = ", ".join(ONTVANGERS)
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(GMAIL_ADRES, GMAIL_APP_PASS)
        server.sendmail(GMAIL_ADRES, ONTVANGERS, msg.as_string())
    print(f"[{datetime.now().strftime('%H:%M')}] Mail verstuurd!")

def maak_html(pool, resultaten, type_rapport="rapport"):
    nu = datetime.now().strftime("%d/%m/%Y om %H:%M")
    pool_naam = pool.get("name", "Mijn zwembad")
    rijen = ""
    for r in resultaten:
        kleur = "#d4edda" if "✅" in r["status"] else ("#f8d7da" if "🚨" in r["status"] else "#fff3cd")
        actie_html = f"<br><small><b>👉 Actie:</b> {r['actie']}</small>" if r["actie"] else ""
        rijen += f"""
        <tr style="background:{kleur}">
            <td style="padding:10px;border-bottom:1px solid #ddd"><b>{r['label']}</b></td>
            <td style="padding:10px;border-bottom:1px solid #ddd">{r['waarde']}{r['eenheid']}</td>
            <td style="padding:10px;border-bottom:1px solid #ddd">{r['ideaal']}</td>
            <td style="padding:10px;border-bottom:1px solid #ddd">{r['status']}{actie_html}</td>
        </tr>"""
    titel = "🚨 KRITIEKE ALERT" if type_rapport == "alert" else "🏊 Zwembad Statusrapport"
    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto">
      <div style="background:#0077b6;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="margin:0">{titel}</h2>
        <p style="margin:5px 0 0">{pool_naam} — {nu}</p>
      </div>
      <table style="width:100%;border-collapse:collapse;margin:0">
        <thead>
          <tr style="background:#023e8a;color:white">
            <th style="padding:10px;text-align:left">Parameter</th>
            <th style="padding:10px;text-align:left">Meting</th>
            <th style="padding:10px;text-align:left">Ideaal</th>
            <th style="padding:10px;text-align:left">Status</th>
          </tr>
        </thead>
        <tbody>{rijen}</tbody>
      </table>
      <div style="background:#f1f1f1;padding:15px;border-radius:0 0 8px 8px;font-size:12px;color:#666">
        Automatisch verstuurd door Zwembad Monitor · Studio Gigant
      </div>
    </body></html>
    """

# ============================================================
# CHECK FUNCTIE
# ============================================================
def zwembad_check():
    uur = datetime.now().hour
    print(f"[{datetime.now().strftime('%d/%m/%Y %H:%M')}] Check gestart...")
    try:
        session = blueriiot_login()
        pool, feed = get_pool_data(session)
        resultaten, kritiek = analyseer(feed)

        if uur in [8, 20]:
            tijdstip = "ochtend" if uur == 8 else "avond"
            html = maak_html(pool, resultaten, "rapport")
            onderwerp = f"🏊 Zwembad rapport {tijdstip} — {datetime.now().strftime('%d/%m/%Y')}"
            stuur_email(onderwerp, html)

        if kritiek:
            html = maak_html(pool, resultaten, "alert")
            onderwerp = f"🚨 KRITIEKE ALERT zwembad — {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            stuur_email(onderwerp, html)

        print("Check klaar.")
    except Exception as e:
        print(f"Fout: {e}")

# ============================================================
# FLASK + SCHEDULER
# ============================================================
@app.route("/")
def home():
    return "🏊 Zwembad Monitor draait! Checks elk uur."

@app.route("/check")
def manual_check():
    zwembad_check()
    return "Check uitgevoerd!"

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(zwembad_check, "interval", hours=1)
    scheduler.start()
    print("🏊 Zwembad Monitor gestart!")
    zwembad_check()  # Meteen eerste check
    app.run(host="0.0.0.0", port=10000)
