#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Build script to create a standalone executable for roguelike.py
This creates a single .exe file that includes all dependencies.
"""

import os
import sys
import subprocess
import shutil

def main():
    # Check if PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing it now...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Build the executable
    print("Building executable...")
    command = [
        "pyinstaller",
        "--onefile",  # Create a single .exe file
        "--windowed",  # Hide the console window when running the GUI version
        "--add-data", f"roguelike.conf{os.pathsep}.",  # Include the config file
        "--name", "RogueLikeSaveProcessor",
        "--icon", "NONE",  # No icon
        "roguelike.py"
    ]
    
    subprocess.check_call(command)
    
    # Copy the .conf file to the output directory
    dist_dir = os.path.join(os.getcwd(), "dist")
    if not os.path.exists(os.path.join(dist_dir, "roguelike.conf")):
        shutil.copy2("roguelike.conf", dist_dir)
    
    print(f"\nExecutable built successfully!")
    print(f"The executable is located at: {os.path.join(dist_dir, 'RogueLikeSaveProcessor.exe')}")
    print("Make sure to keep roguelike.conf in the same directory as the executable.")

if __name__ == "__main__":
    main() 