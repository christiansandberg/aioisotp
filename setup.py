from setuptools import setup, find_packages

with open('aioisotp/version.py') as version:
    exec(version.read())

with open("README.rst") as readme:
    description = readme.read()

# Change pip install to this exact version
description = description.replace(
    "pip install aioisotp",
    "pip install aioisotp==" + __version__)

setup(
    name="aioisotp",
    url="https://github.com/christiansandberg/aioisotp",
    version=__version__,
    packages=find_packages(),
    author="Christian Sandberg",
    author_email="christiansandberg@me.com",
    description="Asyncio implementation of ISO-TP (ISO 15765-2)",
    keywords="CAN ISO-TP 15765",
    long_description=description,
    license="MIT",
    platforms=["any"],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Framework :: AsyncIO",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Intended Audience :: Developers",
        "Topic :: Scientific/Engineering"
    ],
    python_requires=">=3.5",
    install_requires=["python-can~=3.0"],
    include_package_data=True
)
