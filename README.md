# Project Overview

This repository runs an OpenCanary honeypot on an Oracle Cloud Ubuntu instance.
Incoming interactions are logged to a local file; a Discord webhook notifies a channel
in real time whenever credentials or unusual activity are detected. 
Set up involves:

- Spinning up an Ubuntu Server VM on Oracle Cloud.
- Installing and configuring OpenCanary to listen on common honeypot ports (e.g., SSH, Telnet, RDP, VNC).
- Creating a Python virtual environment for dependency isolation.
- Writing a Python script that reads `/var/log/opencanary.log`, increments a byte‐offset file (`ingest.pos`), and inserts new events into SQLite.
- Using pandas to aggregate events, matplotlib to generate bar/pie charts, and the GeoLite2 City database for geolocation.
- Storing metrics in a GitHub repository and automating commits/pushes so that each run updates a Markdown README and accompanying PNG charts.
- Integrating a Discord incoming webhook to receive alerts from OpenCanary when specific credentials are used.

Metrics are aggregated nightly at midnight Eastern Time to provide consistent, daily snapshots.
This ensures that the data reflects uniform 24-hour periods, making it easier to track trends, detect spikes, and compare day-to-day activity.

Below, you’ll find an up-to-date Metrics Report that includes total event counts,
distinct IPs, and breakdowns by port, country, username, and password.

# Metrics Report

<small>All-Time Stats (Last Updated: June 27, 2025 @ 12:01 AM ET)</small>

| Metric         | Value |
|----------------|-------|
| Total events   | 932,488 |
| Distinct IPs   | 2,327 |

![Ports](ports_bar.png)

![Countries](countries_bar.png)

![Usernames](usernames_bar.png)

![Passwords](passwords_bar.png)
