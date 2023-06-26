import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="pytapo",  # Consider following PEP8 package naming recommendations
    version="3.1.13",  # Use semantic versioning principles
    author="Juraj Nyíri",
    author_email="juraj.nyiri@gmail.com",
    description="Python library for communication with Tapo Cameras",
    license="MIT",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/JurajNyiri/pytapo",
    packages=setuptools.find_packages(exclude=["tests", "*.tests", "*.tests.*", "tests.*"]),
    install_requires=["requests", "urllib3", "pycryptodome", "rtp"],
    tests_require=["pytest", "pytest-asyncio", "mock"],
    python_requires='>=3.7',  # specify minimum Python version, adjust as necessary
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
