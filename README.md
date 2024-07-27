# Teddy Autoinstaller

### by Biscgit :heart: 2024

This is a university project with the topic of Bauxine and TonieBoxes.
As of our journey to set up the custom cc3200 firmware and cloud, we were always set back by random issues and sometimes incomplete documentation.
But we are here to help you with that! 

## Features

With this project, we can simplify many common steps!
- dump certificates with auto device detection and without the need of root permissions
- install and setup TeddyCloud with one click
- a diagram to help connect the UART TC2050 cable for firmware dumps

## Installation
Install the required packages from `requirements.txt` with the following command:
```bash
python3 -m pip install -r requirements.txt
```
Run the script with the following command:
```bash
./autoinstaller.py
```
OR (with venv)
```bash
python3 autoinstaller.py
```

## Other tools
Some features depend on my custom implementation of the cc3200tool at Biscgit/cc3200tool.
That library will be automatically downloaded when required after a prompt.

## Disclaimer
NO WARANTIES GIVEN ON ANYTHING PROVIDED. USE AT OWN RISK!
