"""Setup file for kx-hub common utilities."""
from setuptools import setup, find_packages

setup(
    name="kx-common",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "tiktoken==0.5.2",
        "pyyaml>=6.0.1",
    ],
    python_requires=">=3.11",
)
