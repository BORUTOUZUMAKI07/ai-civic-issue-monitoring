import pandas as pd
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset, TargetDriftPreset, DataQualityPreset
from loguru import logger

from common.paths import PROJECT_ROOT

def run_evidently_audit(reference_data_path: str, current_data_path: str, report_name: str = "production_audit"):
    """
    Generates a comprehensive MLOps audit report comparing training data (reference) 
    vs production data (current).
    """
    logger.info(f"📊 Running Evidently AI Audit: {report_name}")
    
    # Load data
    try:
        reference_df = pd.read_csv(reference_data_path)
        current_df = pd.read_csv(current_data_path)
    except Exception as e:
        logger.error(f"Failed to load data for audit: {e}")
        return

    # Initialize Report with multiple presets for a "High Quality" audit
    drift_report = Report(metrics=[
        DataDriftPreset(),      # Detects Feature Drift
        TargetDriftPreset(),    # Detects Label Drift (e.g. suddenly more potholes than usual)
        DataQualityPreset()     # Checks for missing values/outliers in production
    ])

    # Run Analysis
    drift_report.run(reference_data=reference_df, current_data=current_df)

    # Save Output
    output_dir = PROJECT_ROOT / "reports" / "ml_monitoring"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    report_path = output_dir / f"{report_name}.html"
    drift_report.save_html(str(report_path))
    
    logger.success(f"✅ MLOps Report generated at: {report_path}")

if __name__ == "__main__":
    # Example usage for manual trigger
    # run_evidently_audit("data/training_stats.csv", "data/production_stats.csv")
    pass
