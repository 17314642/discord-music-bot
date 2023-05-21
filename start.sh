#!/bin/bash

export BOT_TOKEN="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

python3 -m venv venv
source venv/bin/activate
pip install --upgrade PyNaCl yt-dlp discord.py

python3 main.py
