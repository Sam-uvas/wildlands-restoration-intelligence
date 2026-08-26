<div align="center">

# 🌍 WILDLANDS Restoration Intelligence

<img src="assets/banner wildlands.png" width="100%">

### Geospatial Restoration Intelligence & Environmental Monitoring Platform

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black)
![QGIS](https://img.shields.io/badge/QGIS-589632?style=for-the-badge&logo=qgis&logoColor=white)
![Google Earth Engine](https://img.shields.io/badge/Google%20Earth%20Engine-4285F4?style=for-the-badge&logo=googleearthengine&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![GitHub](https://img.shields.io/badge/GitHub-181717?style=for-the-badge&logo=github&logoColor=white)

---

**Turning geospatial data into restoration intelligence.**

*A geospatial platform designed to connect restoration projects, field observations, satellite-derived environmental indicators, analytics and reporting within a single operational workflow.*

</div>

---
# Dashboard Preview

<p align="center">
<img src="assets/dashboard wildlands.png" width="90%">
</p>

---

# Features

- Interactive geospatial monitoring dashboard
- Restoration project management
- Monitoring site management
- Structured field observation capture
- GPS-based spatial evidence
- Photographic field evidence
- Satellite-derived NDVI monitoring
- Google Earth Engine integration
- Automated geospatial data pipeline
- Environmental analytics
- Restoration reporting
- REST API
- PostgreSQL database integration
- Dockerised backend
- Cloud deployment
- Modern dark interface

---

# Technology Stack

| Category | Technologies |
|-----------|--------------|
| Frontend | HTML5 • CSS3 • JavaScript |
| Backend | Python • FastAPI |
| Database | PostgreSQL |
| GIS | QGIS • Spatial Data |
| Earth Observation | Google Earth Engine • Satellite Data |
| Remote Sensing | NDVI |
| Data Engineering | Python • Automated Processing Pipelines |
| API | REST API • FastAPI |
| Deployment | Docker • Render |
| Version Control | Git • GitHub |

---

# Project Structure

```text
wildlands-restoration-intelligence/
│
├── assets/
│   ├── banner.png
│   └── dashboard.png
│
├── backend/
│   ├── app.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── schema.sql
│
├── dashboard/
│   ├── frontend/
│   │   ├── index.html
│   │   ├── projects.html
│   │   ├── monitoring.html
│   │   ├── field-monitoring.html
│   │   ├── analytics.html
│   │   ├── reports.html
│   │   └── data-management.html
│   │
│   ├── data.json
│   └── field_data.json
│
├── data/
│   ├── sites.gpkg
│   ├── gee_ndvi_data.csv
│   └── gee_trends.csv
│
├── reports/
│   └── restoration_report.pdf
│
├── wildlands_pipeline/
│   ├── config.py
│   ├── sites_setup.py
│   ├── fetch_gee_data.py
│   ├── merge_data.py
│   ├── qgis_report.py
│   └── run_pipeline.py
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
