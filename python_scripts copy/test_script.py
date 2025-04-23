import sys
import os
import platform

def main():
    """
    Simple test script to verify Python execution from Flutter
    """
    print("SUCCESS: Python script executed successfully from Flutter!")
    print("\nPython Version:", sys.version)
    print("Platform:", platform.platform())
    print("Current working directory:", os.getcwd())
    
    # List files in current directory
    print("\nFiles in current directory:")
    for file in os.listdir("."):
        print(f"- {file}")
    
    # Try importing required modules
    try:
        import numpy
        print("\nNumPy is available:", numpy.__version__)
    except ImportError:
        print("\nNumPy is NOT available")
    
    try:
        import cv2
        print("OpenCV is available:", cv2.__version__)
    except ImportError:
        print("OpenCV is NOT available")
    
    try:
        import torch
        print("PyTorch is available:", torch.__version__)
    except ImportError:
        print("PyTorch is NOT available")
    
    return 0

if __name__ == "__main__":
    main() 