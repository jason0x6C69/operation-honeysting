#!/usr/bin/env python3
"""
Ingest OpenCanary logs, build stats & graphs, commit/push to GitHub.
README now includes nightly aggregation details and rationale.
"""

import os
import json
import sqlite3
import pathlib
import subprocess
import datetime

import pandas as pd
import matplotlib.pyplot as plt
import geoip2.database
import matplotlib.patches as mpatches
from geoip2.errors import AddressNotFoundError
from zoneinfo import ZoneInfo

# ---------- Basic Configuration ----------

os.environ.setdefault("MPLCONFIGDIR", "/tmp/.mplconfig")

HOME = pathlib.Path("/opt/canary-reporter")
LOG = pathlib.Path("/var/log/opencanary.log")
DB = HOME / "stats.db"
REPO = HOME / "repo"
MMDB = "/usr/share/GeoIP/GeoLite2-City.mmdb"

GITHUB_TOKEN = os.environ.get("GITHUB_PAT", "")
GIT_URL = (
    f"https://{GITHUB_TOKEN}:x-oauth-basic"
    "/github.com/jason0x6C69/operation-honeysting.git"
)

# ---------- Clone & Configure Repository ----------

if not REPO.exists():
    subprocess.run(["git", "clone", GIT_URL, str(REPO)], check=True)

subprocess.run(
    ["git", "-C", str(REPO), "config", "user.name", "Honeysting Bot"],
    check=True
)
subprocess.run(
    ["git", "-C", str(REPO), "config", "user.email", "bot@users.noreply.github.com"],
    check=True
)
subprocess.run(
    ["git", "-C", str(REPO), "remote", "set-url", "origin", GIT_URL],
    check=True
)

# Sync to origin/main
subprocess.run(["git", "-C", str(REPO), "fetch"], check=False)
subprocess.run(
    ["git", "-C", str(REPO), "reset", "--hard", "origin/main"],
    check=False
)

# ---------- Initialize Database ----------

with sqlite3.connect(DB) as cx:
    cx.execute("""
        CREATE TABLE IF NOT EXISTS events (
            ts TEXT,
            port INTEGER,
            ip TEXT,
            username TEXT,
            password TEXT
        )
    """)

# ---------- Incremental Log Ingest ----------

pos_file = HOME / "ingest.pos"
start = int(pos_file.read_text()) if pos_file.exists() else 0

with LOG.open() as fh:
    fh.seek(start)
    new_data = fh.read()

# Update file-read cursor
pos_file.write_text(str(start + len(new_data)))

for line in new_data.splitlines():
    line = line.strip()
    if not line.startswith("{"):
        continue

    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        continue

    dst_port = ev.get("dst_port", -1)
    if dst_port == -1:
        continue

    logdata = ev.get("logdata", {}) or {}
    user = ""
    pwd = ""

    # Extract username/password from nested logdata
    for key, val in logdata.items():
        key_lower = key.lower()
        if key_lower in ("username", "user") and val:
            user = str(val)
        if "password" in key_lower and val:
            pwd = str(val)
        if user and pwd:
            break

    # Fallback to top-level fields
    if not user:
        user = ev.get("username") or ev.get("user", "")
    if not pwd:
        pwd = ev.get("password", "")

    with sqlite3.connect(DB) as cx:
        cx.execute(
            "INSERT INTO events VALUES (?,?,?,?,?)",
            (
                ev.get("local_time", ""),
                dst_port,
                ev.get("src_host", ""),
                user,
                pwd
            )
        )

# ---------- Data Analysis & Geolocation ----------

df = pd.read_sql("SELECT * FROM events", sqlite3.connect(DB))
unique_ips = df["ip"].nunique()

# Count hits per port and map to protocol names
by_port = df["port"].value_counts()
port_names = {
    21: "FTP", 22: "SSH", 23: "Telnet", 80: "HTTP", 123: "NTP",
    161: "SNMP", 443: "HTTPS", 1433: "MSSQL", 3306: "MySQL",
    3389: "RDP", 5900: "VNC"
}

# Geolocate each IP
countries = []
with geoip2.database.Reader(MMDB) as geo:
    for ip in df["ip"]:
        try:
            country = geo.city(ip).country.name or "Unknown"
        except (AddressNotFoundError, ValueError):
            country = "Unknown"
        countries.append(country)
df["country"] = countries

by_country = df["country"].value_counts().head(10)

# Top usernames/passwords
valid_users = (
    df["username"]
    .dropna().astype(str)
    .str.strip()
    .loc[lambda s: (s != "") & (s.str.lower() != "none")]
    .value_counts()
    .head(10)
)

valid_passwords = (
    df["password"]
    .dropna().astype(str)
    .str.strip()
    .loc[lambda s: (s != "") & (s != "<Password was not in the common list>")]
    .value_counts()
    .head(10)
)

# ---------- Chart-saving Helper ----------

def save_chart(series, kind, title, outfile, rotate=False):
    plt.figure()
    if series.empty or series.sum() == 0:
        plt.text(0.5, 0.5, "No data yet", ha="center", va="center")
        plt.axis("off")
    else:
        if kind == "pie":
            series.plot(kind="pie", autopct="%1.0f%%", ylabel="")
        else:
            series.plot(kind="bar")
            if rotate:
                plt.xticks(rotation=65, ha="right")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(outfile, bbox_inches="tight")
    plt.close()

# Ports bar chart
protocols = [port_names.get(p, str(p)) for p in by_port.index]
colors = plt.get_cmap("tab20")(range(len(protocols)))

fig, ax = plt.subplots(figsize=(6, 4))
ax.bar(protocols, by_port.values, color=colors)
ax.set_title("Ports Hit")
ax.set_xlabel("Protocol")
ax.set_ylabel("Count")
ax.legend(
    handles=[mpatches.Patch(color=colors[i], label=protocols[i]) for i in range(len(protocols))],
    title="Port → Protocol",
    loc="upper right"
)
fig.savefig(REPO / "ports_bar.png", bbox_inches="tight")
plt.close(fig)

# Other charts
save_chart(by_country,   "bar",  "Top Source Countries",  REPO / "countries_bar.png", rotate=True)
save_chart(valid_users,  "bar",  "Most Common Usernames", REPO / "usernames_bar.png", rotate=True)
save_chart(valid_passwords, "bar", "Most Common Passwords", REPO / "passwords_bar.png", rotate=True)

# ---------- Update README & Push Changes ----------

# Timestamp in Eastern Time
now_et = datetime.datetime.now(ZoneInfo("America/New_York"))
timestamp_et = now_et.strftime("%B %-d, %Y @ %-I:%M %p ET")

with (REPO / "README.md").open("w") as md:
    md.write(f"""# Project Overview

This repository runs an OpenCanary honeypot on an Oracle Cloud Ubuntu instance.
...
Metrics are aggregated nightly at midnight Eastern Time to provide consistent, daily snapshots.

# Metrics Report

<small>All-Time Stats (Last Updated: {timestamp_et})</small>

| Metric         | Value |
|----------------|-------|
| Total events   | {len(df):,} |
| Distinct IPs   | {unique_ips:,} |

![Ports](ports_bar.png)
![Countries](countries_bar.png)
![Usernames](usernames_bar.png)
![Passwords](passwords_bar.png)
""")

# Commit & push
subprocess.run(["git", "-C", str(REPO), "add", "-A"], check=False)
subprocess.run(
    ["git", "-C", str(REPO), "commit", "-m", f"auto: {datetime.datetime.utcnow().isoformat()}"],
    check=False
)
subprocess.run(["git", "-C", str(REPO), "push"], check=True)
