#!/bin/bash

export BOT_TOKEN="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

source bin/activate
pip install --upgrade PyNaCl youtube_dl discord.py

python3 main.py
