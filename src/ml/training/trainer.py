import torch
from tqdm import tqdm
from rich.console import Console

console = Console()

def train_one_epoch(model, dataloader, optimizer, criterion, device):
    model.train()
    running_loss = 0.0

    progress = tqdm(dataloader, leave=False)

    for images, labels in progress:
        images, labels = images.to(device), labels.to(device)

        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()

        running_loss += loss.item()
        progress.set_postfix(loss=loss.item())

    avg_loss = running_loss / len(dataloader)
    console.log(f"[green]Epoch completed[/green] - Avg Loss: {avg_loss:.4f}")

    return avg_loss

def validate_one_epoch(model, dataloader, criterion, device):
    model.eval()
    running_loss = 0.0
    
    with torch.no_grad():
        for images, labels in dataloader:
            images, labels = images.to(device), labels.to(device)
            outputs = model(images)
            loss = criterion(outputs, labels)
            running_loss += loss.item()
            
    avg_loss = running_loss / len(dataloader) if len(dataloader) > 0 else 0.0
    console.log(f"[blue]Validation completed[/blue] - Avg Loss: {avg_loss:.4f}")
    return avg_loss
