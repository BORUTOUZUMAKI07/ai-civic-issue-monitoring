import os
import inspect
import sys

# 1. Inspect the Class Definition
print("--- 1. Inspecting 'evidently.core.report.Report' ---")
try:
    from evidently.core.report import Report
    print(f"Imported Report: {Report}")
    print("Methods starting with 'save':")
    for m in dir(Report):
        if "save" in m:
            print(f"  - {m}")
            
    print("Methods starting with 'json':")
    for m in dir(Report):
        if "json" in m:
            print(f"  - {m}")

except ImportError:
    print("Could not import evidently.core.report.Report")
except Exception as e:
    print(f"Error inspecting class: {e}")

# 2. Read Source Code
print("\n--- 2. Reading Source Code Context ---")
try:
    import evidently.core.report
    source_file = evidently.core.report.__file__
    print(f"Source file: {source_file}")
    
    with open(source_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    for i, line in enumerate(lines):
        if "def save_html" in line:
            print(f"\n[Line {i+1}] Found 'def save_html':")
            # Print 5 lines before to see indentation/context
            for j in range(max(0, i-5), i+1):
                print(f"  {j+1}: {lines[j].rstrip()}")
            # Print the line itself
            print(f"  {i+1}: {line.rstrip()}")
            
except Exception as e:
    print(f"Error reading source: {e}")
