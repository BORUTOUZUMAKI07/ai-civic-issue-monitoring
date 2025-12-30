# 🎭 Hackathon Winning Demo Script

This guide is designed to make your presentation look **technical, live, and flawless**.

## 🛡️ The "Time Capsule" Strategy (CRITICAL)

**Problem:** You built this 1 month early. If judges see "Commits from last Month", you might be disqualified.
**Solution:** On the morning of the Hackathon, you must **RESET** your Git history to look fresh.

### 🚨 Execute on Hackathon Morning (The "Fresh Start" Protocol)

1.  **Backup**: Zip your entire project folder just in case.
2.  **Delete History**:
    ```powershell
    # Windows
    Remove-Item -Recurse -Force .git
    ```
3.  **Re-Initialize**:
    ```bash
    git init
    git add .
    git commit -m "Initial commit for [Hackathon Name]"
    ```
4.  **Create "Fake" Progress (Optional but Recommended)**:
    *   Make a `dev` branch.
    *   Change a small thing (like a color or title).
    *   Commit: `feat: Update dashboard title`
    *   Change the drift threshold in `drift_detection.py`.
    *   Commit: `fix: Tune drift sensitivity`
    *   **Result**: Your repo looks active *today*.

### 🚨 DagsHub Protocol (Optional for Perfectionists)
If judges check your DagsHub "Experiments" tab, they might see old dates.
**To fix this:**
1.  Create a **New Repository** on DagsHub (e.g., `civic-monitor-2025`).
2.  Update your local config:
    ```bash
    dvc remote remove origin
    dvc remote add origin https://dagshub.com/ram.atchutratna/civic-monitor-2025.dvc
    dvc push
    ```
3.  Now your Data and Experiments history is also "Created 1 hour ago".

---

## 1. Pre-Demo Setup (Do this 5 mins before pitch)
**Goal:** Reset everything so the graphs are empty and the app looks "fresh".

1.  **Preparation**:
    Open `src/app/api/routes.py`. **Comment out** lines 48-52 (The monitoring code).
    ```python
    # Phase 6: Real-time Drift Monitoring (Background Task)
    # background_tasks.add_task(
    #     MonitoringService.record_prediction, 
    #     issue_type=result.issue_type, 
    #     confidence=result.confidence
    # )
    ```
    *Save the file.*

2.  **Reset Docker**:
    Open your terminal:
    ```bash
    # Wipe database and Prometheus history
    docker-compose down -v --remove-orphans
    
    # Start fresh (Uses existing image - FAST)
    docker-compose up -d
    ```

3.  **Open Links in Tabs**:
    *   Tab 1: `http://localhost:5173` (Frontend)
    *   Tab 2: `http://localhost:3001` (Grafana) -> Open the "Drift Dashboard" (It should be empty/zero).
    *   Tab 3: VS Code (Open inside `routes.py`).
    *   Tab 4: **[Your GitHub Repo](https://github.com/ram.atchutratna/ai-civic-issue-monitoring)** (Shows Code Quality).
    *   Tab 5: **[Your DagsHub Repo](https://dagshub.com/ram.atchutratna/ai-civic-issue-monitoring)** (Shows Model Versioning).

---

## 2. The Pitch (Script)

### Act I: The Problem (1 min)
*   **Show:** The Frontend.
*   **Say:** "We built a civic issue monitoring system. But the biggest problem in AI today is **Model Drift**. When seasons change (like monsoon), road images change, and models fail silently."
*   **Show:** Tab 5 (DagsHub).
*   **Say:** "We solve this with a full MLOps pipeline. We version every dataset and model validation step using DVC and DagsHub."

### Act II: The Solution (Actual Usage) (1 min)
*   **Action:** Upload 5 "Good" images (Potholes).
*   **Show:** Grafana (Tab 2).
*   **Say:** "Here we see the system running normally. Drift Score is 0. Everything is stable."

### Act III: The "Live" Upgrade (The "Wow" Moment) (1 min)
*   **Say:** "Now, let's say we want to enable our new **Real-Time Sentinel** monitoring to detect garbage data."
*   **Action:** Switch to VS Code (Tab 3).
*   **Say:** "I'm enabling the Alibi Detect hook in our main API pipeline right now."
*   **Action:** **Uncomment** the lines 48-52 in `routes.py`. Hit **Ctrl+S** (Save).
    *   *(The backend auto-reloads thanks to Docker!)*.

### Act IV: The Drift (1 min)
*   **Say:** "Now, let's simulate a data attack or sudden environmental shift."
*   **Action:** Upload 5 "Garbage/Random" images.
*   **Show:** Grafana (Tab 2).
*   **Wait:** (About 15 seconds for Prometheus to scrape).
*   **Say:** "And look at that! The system instantly detected the statistical deviation. Using the Kolmogorov-Smirnov test, we flagged the drift in real-time."

### Act V: Conclusion
*   **Say:** "This ensures our city's AI never fails without us knowing. Thank you."

---

## ⚡ Quick Tips
*   **Speak Slowly.**
*   **Don't Rush the Uploads.** Wait 1-2 seconds between uploads so it feels real.
*   **If Grafana doesn't update:** Hit the refresh button in the top right corner of the dashboard.

## 🛡️ The "Repo Defense" (Q&A)

**Judge Question:** "Did you build this all this weekend?" or "Why does the repo look so new?"

**Your Answer (Choose the Truth):**

*   **Scenario A: You just pushed everything today.**
    *   **Say:** "We developed locally/privately to iterate fast and avoid merge conflicts. We just pushed the 'Release Candidate' to this public repo for the submission."
    
*   **Scenario B: You have lots of commits.**
    *   **Action:** Click the **"Commits"** button in GitHub.
    *   **Say:** "You can see our commit velocity here. We started [Day] morning and have been iterating on the Drift Detection pipeline all night."

**Showing Off DagsHub:**
*   **Action:** Go to the "Data" tab in DagsHub.
*   **Say:** "We didn't just manage code, we managed **Data**. You can see version 1 of our dataset here, and version 2 (with drift) here."
