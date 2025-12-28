from torchvision import datasets, transforms
from torch.utils.data import DataLoader

def to_rgb(img):
    return img.convert("RGB")

def get_dataloaders(data_dir, batch_size=32, train_split=0.7, val_split=0.15):
    # Robust transform for training (handles color variations)
    train_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomGrayscale(p=0.2), # Mimics B&W variations
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
        transforms.Lambda(to_rgb),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])

    # Standard transform for val/test
    val_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.Lambda(to_rgb),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])

    # Load dataset twice to apply different transforms
    full_dataset = datasets.ImageFolder(root=data_dir)
    classes = full_dataset.classes
    
    print(f"📦 Data Directory: {data_dir}")
    print(f"🔍 Found {len(classes)} classes: {classes}")
    
    if len(classes) != 4:
        print(f"❌ ERROR: Expected 4 classes, but found {len(classes)}!")
        print(f"   Check your data path: {data_dir}")
    # Calculate split lengths
    num_data = len(full_dataset)
    train_size = int(train_split * num_data)
    val_size = int(val_split * num_data)
    
    # Split indices (Deterministic)
    import torch
    indices = torch.randperm(num_data).tolist()
    train_indices = indices[:train_size]
    val_indices = indices[train_size:train_size+val_size]
    test_indices = indices[train_size+val_size:]
    
    # Create Subsets with specific transforms
    from torch.utils.data import Subset
    
    train_dataset = Subset(datasets.ImageFolder(root=data_dir, transform=train_transform), train_indices)
    val_dataset = Subset(datasets.ImageFolder(root=data_dir, transform=val_transform), val_indices)
    test_dataset = Subset(datasets.ImageFolder(root=data_dir, transform=val_transform), test_indices)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=2)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=2)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False, num_workers=2)

    return train_loader, val_loader, test_loader, classes
