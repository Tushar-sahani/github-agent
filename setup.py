from setuptools import setup, find_packages

setup(
    name="github-agent",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "openai",
        "python-dotenv",
        "typer"
    ],
    entry_points={
        "console_scripts": [
            "github-agent=github_agent.main:app"
        ]
    },
    python_requires=">=3.8"
)