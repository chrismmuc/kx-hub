"""
Entry point for running clustering as a module.

Usage:
    python3 -m src.clustering.initial_load [--dry-run]
"""

from .initial_load import main

if __name__ == '__main__':
    main()
