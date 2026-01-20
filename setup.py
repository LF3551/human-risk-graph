"""
Human Risk Graph (HRG) - A quantitative model for organizational security risk
"""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="human-risk-graph",
    version="0.1.2",
    author="Aleksei Aleinikov",
    author_email="adk3551@gmail.com",
    description="A quantitative model for measuring organizational security risk caused by human dependencies",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/LF3551/human-risk-graph",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Topic :: Security",
        "Topic :: Scientific/Engineering",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "networkx>=3.0",
        "numpy>=1.24.0",
        "scipy>=1.10.0",
        "click>=8.1.0",
        "pyvis>=0.3.2",
        "matplotlib>=3.7.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "black>=23.0.0",
            "mypy>=1.0.0",
            "flake8>=6.0.0",
            "bandit>=1.7.0",
        ],
        "experiments": [
            "pandas>=2.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "hrg=src.cli:main",
        ],
    },
)
