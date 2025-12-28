import torch
from sklearn.metrics import classification_report, confusion_matrix
import mlflow
import numpy as np
from loguru import logger
from ml.utils.device import get_device

def evaluate_model(model, dataloader, class_names):
    """
    Evaluates the model on a given dataloader and logs results to MLflow.
    """
    device = get_device()
    model.eval()
    
    all_preds = []
    all_labels = []

    with torch.no_grad():
        for images, labels in dataloader:
            images, labels = images.to(device), labels.to(device)
            outputs = model(images)
            _, preds = torch.max(outputs, 1)
            
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(labels.cpu().numpy())

    # Calculate metrics
    report = classification_report(
        all_labels, 
        all_preds, 
        target_names=class_names, 
        output_dict=True
    )
    
    # Log metrics to MLflow
    for key, value in report.items():
        if isinstance(value, dict):
            for k, v in value.items():
                mlflow.log_metric(f"eval_{key}_{k}", v)
        else:
            mlflow.log_metric(f"eval_{key}", value)

    logger.info("Evaluation completed. Metrics logged to MLflow.")
    return report

if __name__ == "__main__":
    # Example standalone usage if needed
    pass
