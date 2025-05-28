#!/usr/bin/env python3
"""
Canada Food Guide Recipe Scraper

A tool to search and download recipes from the Canada Food Guide website.
"""

from src.cli import FoodGuideCLI

def main():
    cli = FoodGuideCLI()
    cli.run()

if __name__ == "__main__":
    main()