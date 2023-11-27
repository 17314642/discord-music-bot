#!/bin/bash

export BOT_TOKEN="$(tr -d '\n' < token.txt)"

python3 -m venv venv
source venv/bin/activate
pip install --upgrade PyNaCl yt-dlp discord.py

python3 main.py
