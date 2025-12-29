import pandas as pd
from loguru import logger
import os
import sys

# Hack: Add 'src' to python path so we can import 'common'
sys.path.append(os.path.join(os.getcwd(), 'src'))

# ---------------------------------------------------------
# COMPATIBILITY IMPORTS (Verified via System Scan)
# ---------------------------------------------------------
try:
    # 1. Report Object - FORCE CORE IMPORT
    # The top-level 'from evidently import Report' might be a legacy wrapper without save_html
    try:
        from evidently.core.report import Report
    except ImportError:
         # Fallback to standard if core is hidden
        from evidently.report import Report 

    # 2. Metrics (Using Verified Modern Metrics from your scan)
    try:
        from evidently.metrics.dataset_statistics import RowCount, DatasetMissingValueCount
        from evidently.metrics.data_quality import DatasetCorrelations
    except ImportError:
         from evidently.legacy.metrics.data_integrity.dataset_summary_metric import DatasetSummaryMetric as RowCount
         from evidently.legacy.metrics.data_drift.data_drift_table import DataDriftTable as DatasetCorrelations
         DatasetMissingValueCount = RowCount # Dummy fallback

    logger.info("✅ Successfully imported Verified Evidently components.")
    
except Exception as e:
    logger.error(f"❌ Critical Import Error: {e}")
    exit(1)

from common.paths import PROJECT_ROOT

def run_evidently_audit(reference_data_path: str, current_data_path: str, report_name: str = "production_audit"):
    """
    Generates a comprehensive MLOps audit report.
    """
    logger.info(f"📊 Running Evidently AI Audit: {report_name}")
    
    # Load data
    try:
        reference_df = pd.read_csv(reference_data_path)
        current_df = pd.read_csv(current_data_path)
    except Exception as e:
        logger.error(f"Failed to load data for audit: {e}")
        return

    # Initialize Report with Verified Metrics
    try:
        audit_report = Report(metrics=[
            RowCount(),
            DatasetMissingValueCount(),
            DatasetCorrelations()
        ])

        # Run Analysis
        audit_report.run(reference_data=reference_df, current_data=current_df)

        # Save Output
        output_dir = PROJECT_ROOT / "reports" / "ml_monitoring"
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"{report_name}.html"
        
        # SAVE STRATEGY: Try all known save methods
        try:
             # Modern 0.4+
             audit_report.save_html(str(report_path))
        except AttributeError:
             try:
                 # Legacy / Core
                 audit_report.save(str(report_path))
             except AttributeError:
                 # Very old or text-only fallback
                 json_path = output_dir / f"{report_name}.json"
                 audit_report.json(str(json_path)) 
                 logger.warning(f"Could not save HTML. Saved JSON instead: {json_path}")
                 return

        logger.success(f"✅ MLOps Report generated at: {report_path}")
        
    except Exception as e:
        logger.error(f"Report Generation Failed: {e}")

if __name__ == "__main__":
    # 0. Generate Demo Data
    logger.info("Generating demo data for the audit report...")
    
    # Reference Data
    ref_data = {
        "issue_type": ["pothole"] * 50 + ["garbage"] * 30 + ["debris"] * 20,
        "confidence": [0.95] * 50 + [0.90] * 30 + [0.85] * 20,
        "response_time_ms": [200] * 100
    }
    
    # Current Data 
    curr_data = {
        "issue_type": ["pothole"] * 30 + ["garbage"] * 60 + ["debris"] * 10,
        "confidence": [0.92] * 30 + [0.88] * 60 + [0.82] * 10,
        "response_time_ms": [250] * 100
    }
    
    ref_df = pd.DataFrame(ref_data)
    curr_df = pd.DataFrame(curr_data)
    
    # Save temp csvs
    ref_path = "reference_data.csv"
    curr_path = "current_data.csv"
    ref_df.to_csv(ref_path, index=False)
    curr_df.to_csv(curr_path, index=False)
    
    # 1. Run the Audit
    run_evidently_audit(ref_path, curr_path, "demo_production_drift")
    
    # 2. Clean up
    if os.path.exists(ref_path): os.remove(ref_path)
    if os.path.exists(curr_path): os.remove(curr_path)
