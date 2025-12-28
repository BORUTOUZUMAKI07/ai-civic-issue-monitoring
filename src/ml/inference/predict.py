import argparse
from PIL import Image
from app.core.inference import predict_issue
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()

def run_prediction(image_path: str):
    path = Path(image_path)
    if not path.exists():
        console.print(f"[red]Error: File {image_path} not found.[/red]")
        return

    image = Image.open(path)
    result = predict_issue(image)

    table = Table(title=f"Prediction for {path.name}")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="magenta")
    
    table.add_row("Class label", result["label"])
    table.add_row("Confidence", str(result["confidence"]))
    
    console.print(table)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run inference on a single image.")
    parser.add_argument("image", type=str, help="Path to the image file.")
    args = parser.parse_args()
    
    run_prediction(args.image)
