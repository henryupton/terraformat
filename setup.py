from setuptools import setup, find_packages

# Read the contents of your README file
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="terraformat",
    version="0.1.4",
    author="Henry Upton-Birdsall",
    author_email="henryupton@gmail.com",
    description="A wrapper for the Terraform CLI that provides a formatted plan summary.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/henryupton/terraformat",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Build Tools",
    ],
    install_requires=[
        'click',
        'tabulate',
    ],
    extras_require={
        "test": ["pytest"],
    },
    entry_points={
        'console_scripts': [
            'terraformat = terraformat.main:cli',
        ],
    },
    python_requires='>=3.7',
)
