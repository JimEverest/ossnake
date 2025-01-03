from setuptools import setup, find_packages

setup(
    name="ossnake",
    version="0.1.0",
    author="Jim Everest",
    author_email="tianwai263@gmail.com",
    description="A unified object storage browser",
    long_description=open("readme.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/jimeverest/ossnake",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "boto3",
        "oss2",
        "minio",
        "tkinter",
        "pillow",
        "python-vlc",
        "requests",
        "tkinterdnd2",
        "colorama",
        "pydantic",
        "pytest",
        "pytest-html",
        "pytest-cov",
        "pywin32"
    ],
    entry_points={
        'console_scripts': [
            'ossnake=ossnake.main:main',
        ],
    },
) 