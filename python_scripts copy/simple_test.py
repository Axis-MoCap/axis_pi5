#!/usr/bin/env python3
import os
import sys

def main():
    print("Python simple test executed successfully!")
    print(f"Python version: {sys.version}")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Files in current directory:")
    for item in os.listdir('.'):
        print(f"- {item}")
    
    return 0

if __name__ == "__main__":
    main() 