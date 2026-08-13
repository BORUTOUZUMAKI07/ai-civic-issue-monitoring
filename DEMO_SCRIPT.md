# Demo Script

A live walkthrough of the CivicPulse platform for the Vadodara Municipal Corporation.

## 1. Pre-Demo Setup (5 minutes before)

1. Start the backend:
   ```bash
   pixi run start
   ```
2. Start the frontend:
   ```bash
   pixi run frontend
   ```
3. Verify:
   - Frontend: http://localhost:3000
   - Backend API docs: http://localhost:8000/docs
   - Health check: `Invoke-RestMethod http://localhost:8000/health` (should show `"database": true`)
4. Login with a field-worker account (create one via the Register page if needed).

## 2. The Pitch (Script)

### Act I: The Problem (1 min)
- **Show:** The Login page, then the Dashboard.
- **Say:** "Civic issues like potholes and garbage are identified only through citizen complaints. Many issues go unnoticed for days, with no automated detection or priority-based routing."

### Act II: The Solution — Live Dashboard (1 min)
- **Show:** Dashboard (already logged in).
- **Say:** "Field workers capture issues with their phones. The system auto-classifies each one with AI, maps it to its ward via GPS geo-fencing, and routes it to the right engineer."
- **Point to:** KPI cards (Total Reports, In Progress, Assigned, Resolved), the Issue Status donut, Issues by Category chart, and Top Wards.
- **Say:** "Every number here updates live from the platform's real-time feed."

### Act III: The Report Flow (1.5 min)
- **Show:** Issues page → click "Report an issue".
- **Action:** Upload a photo (GPS coordinates are read from the image, falling back to device location, then a manual map picker).
- **Say:** "The report is classified immediately and assigned to the correct ward."
- **Show:** The issue detail page.
- **Point to:** the detected category, detection confidence bar, severity, "Similar reports" list, and the Actions panel.
- **Say:** "The AI also finds similar past reports so engineers can see recurring problem areas."

### Act IV: Resolution Lifecycle (1 min)
- **Show:** The Actions panel on an open issue.
- **Say:** "An issue moves through a clear lifecycle — assigned to an engineer, work starts, then the engineer uploads a resolution photo to close it."
- **Show:** The Timeline card, then the dashboard KPI updates.

### Act V: The MLOps Backbone (1 min)
- **Show:** DagsHub / GitHub repo.
- **Say:** "Under the hood this is a full MLOps pipeline. Every dataset and model is versioned with DVC, experiments are tracked with MLflow on DagsHub, and scheduled drift detection retrains the model when real-world images shift — for example during monsoon season."
- **Conclude:** "So the city's AI never fails silently. Thank you."

## 3. Quick Tips

- Speak slowly; let each page load before moving on.
- Wait 1–2 seconds between uploads so updates feel real.
- If the Issues page shows "Offline", the WebSocket reconnects automatically — it's the live-feed badge, not an error.
- Use the Map page to show citywide coverage; the floating badge shows total reports and categories.

## 4. Q&A Notes

- **"How does classification work?"** — A computer-vision model (trained on civic-issue photos) classifies the issue; a keyword classifier is the fallback for text-only reports. Low-confidence reports are flagged for review.
- **"How do you handle bad GPS?"** — If photo/device coordinates are missing, the field worker drops a pin on the map; the nearest ward is derived from geo-fencing.
- **"What makes this production-ready?"** — Hosted Postgres + Redis, containerized deploy, CI/CD with GitHub Actions, DVC versioning, MLflow experiment tracking, and scheduled drift monitoring.
