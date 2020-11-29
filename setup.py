import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="pytapo",
    version="1.2.1",
    author="Juraj Nyíri",
    author_email="juraj.nyiri@gmail.com",
    description="Python library for communication with Tapo Cameras",
    license="MIT",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/JurajNyiri/pytapo",
    packages=setuptools.find_packages(),
    install_requires=["requests", "urllib3"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
