# PU Code Hackathon 3.0 - PPT Content

> **IMPORTANT:** Max 4 slides. Use bullet points. Save as PDF.

---

## SLIDE 1: Basic Details

| Field | Value |
| :--- | :--- |
| **Problem Statement Title** | AI-Based Civic Issue Monitoring System |
| **Track Name** | Smart Energy Monitoring & Optimization System |

---

## SLIDE 2: Idea / Solution Description

### The Problem
- Current civic issues (potholes, garbage, debris) are identified through citizen complaints
- Many issues remain unidentified for days/weeks
- No automated detection or priority-based routing

### Our Solution
- AI-powered mobile app for VMC field employees
- Auto-classifies issues using Computer Vision (PyTorch)
- Geo-fencing maps location to 19 Vadodara wards
- Auto-routes to concerned engineer (ward-wise teams)
- Engineers upload resolution photo to close issues

### Process Flow
```
[Employee Captures Image] → [AI Classification] → [Geo-fencing (19 Wards)] → [Auto-Route to Engineer] → [Resolution Upload] → [Issue Closed]
```

### Technology Stack
| Layer | Technology |
| :--- | :--- |
| **Frontend** | Next.js 16 + Tailwind v4 + shadcn/ui (PWA-ready) |
| **Backend** | FastAPI (Python) |
| **ML Model** | PyTorch + Transformers |
| **Containerization** | Docker + Docker Compose |
| **Monitoring** | New Relic APM + Statistical Drift Detection (Prefect) |
| **MLOps** | DVC + DagsHub + GitHub Actions |

---

## SLIDE 3: Use Cases & Unique Features

### Use Cases
1. **Field Survey**: VMC employees survey city on two-wheelers, capture issues via app
2. **Auto-Detection**: System identifies issue type (pothole/garbage/debris) automatically
3. **Smart Routing**: Issue sent to correct ward engineer based on GPS coordinates
4. **Resolution Tracking**: Engineer uploads "after" photo to mark issue resolved
5. **Real-Time Monitoring**: Dashboard shows all open/resolved issues citywide

### Unique Value Proposition (What Makes Us Different)
- **Real-Time Drift Monitoring**: Scheduled statistical drift detection alerts if the AI model's confidence/labels shift from baseline (e.g., monsoon changes road images)
- **Proactive Alerts**: New Relic alerts when model confidence drops
- **Enterprise MLOps**: Data versioning (DVC) + Experiment tracking (DagsHub)
- **Production-Ready**: CI/CD, Docker, New Relic monitoring included

---

## SLIDE 4: Dependencies & Future Scope

### Dependencies / Show Stoppers
1. **Internet Connectivity**: App requires internet for AI inference and routing
2. **GPS Accuracy**: Geofencing depends on accurate location data
3. **Training Data**: Model accuracy depends on quality training images

### Mitigation Strategies
- Offline mode for image capture, sync when connected
- Fallback to nearest ward if GPS is inaccurate
- Continuous model improvement with new field data

### Future Scope / Business Potential
- Add more classes: Stray cattle, Open manholes, Street light faults
- Citizen portal for public issue reporting
- SMS/WhatsApp alerts to engineers
- Analytics dashboard for VMC leadership
- Can be deployed to any Municipal Corporation in India (SaaS model)

---

## ABSTRACT (Separate Submission)

> The AI-Based Civic Issue Monitoring System is a production-grade solution for Vadodara Municipal Corporation to proactively identify and resolve civic issues. Field employees capture images using a mobile PWA, which are automatically classified using a PyTorch-based Computer Vision model. The system uses geo-fencing to map issues to Vadodara's 19 administrative wards and auto-routes them to concerned engineers. Engineers close issues by uploading resolution photos. The system includes scheduled statistical drift detection, enterprise monitoring (New Relic), and a full CI/CD pipeline. Built with FastAPI, Next.js, Docker, and MLOps best practices (DVC, DagsHub).
