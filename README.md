# Smart Glasses for Visually Impaired People

## Overview

Smart Glasses is an academic assistive technology prototype designed to help visually impaired people detect obstacles and receive real-time audio guidance.
The system uses a Raspberry Pi camera, YOLO object detection, text-to-speech feedback, an emergency push button, GPS module, and Telegram location sharing to improve user safety and navigation.

## Features

* Real-time object detection using YOLO
* Audio feedback for obstacle warnings
* Direction-based guidance: left, right, and ahead
* Emergency push button
* GPS location reading
* Emergency location sharing through Telegram
* Raspberry Pi camera integration

## Hardware Used

* Raspberry Pi
* Raspberry Pi Camera
* GPS Module
* Emergency Push Button
* Speaker / Earphones

## Technologies Used

* Python
* Raspberry Pi
* PiCamera2
* YOLO / Ultralytics
* OpenCV
* pyttsx3 Text-to-Speech
* GPIO
* Serial Communication
* Telegram Bot API

## How It Works

The camera captures live frames from the environment. YOLO detects objects in the frame, then the program checks whether the obstacle is on the left, right, or center. Based on the obstacle position and size, the system gives audio instructions such as moving left, moving right, or slowing down.

When the emergency button is pressed, the system tries to read the GPS location and sends it through Telegram.

## How to Run

1. Install the required Python libraries:

```bash
pip install -r requirements.txt
```

2. Add your own Telegram bot token and chat ID inside the Python file:

```python
TELEGRAM_BOT_TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "PUT_YOUR_CHAT_ID_HERE"
```

3. Run the main prototype code:

```bash
python smart_glasses_main.py
```

## Project Files

* `smart_glasses_main.py`: main prototype code
* `smart_glasses_threaded_experimental.py`: experimental threaded version designed to improve performance
* `requirements.txt`: required Python libraries
* `.gitignore`: files ignored by Git

## Team Members

* Cynthia Issa
* Assil Sabbagh
* Fawzi Rabah
* Hala Al Tabech


## Note

This is an academic prototype. Private credentials such as Telegram bot tokens and chat IDs were removed from the public version for security.
The project is designed to run on Raspberry Pi hardware with the required camera, GPS module, button, and audio output connected.

