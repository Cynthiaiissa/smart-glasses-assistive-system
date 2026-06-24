# Smart Glasses for Visually Impaired People

## Overview

Smart Glasses is an academic assistive technology prototype designed to help visually impaired people detect obstacles and receive real-time audio guidance.
The system uses a Raspberry Pi camera, YOLO object detection, text-to-speech feedback, an emergency push button, GPS module, and Telegram location sharing to improve user safety and navigation.

## Project Images

### Location showing
![Location Showing](images/image1.jpg)

### Hardware Setup
![Hardware Setup](images/image2.jpg)

### Prototype
![Project Prototype](images/image3.jpg)

## Features

* Real-time object detection using YOLO
* Audio feedback for obstacle warnings
* Direction-based guidance: left, right, and ahead
* Emergency push button for safety alerts
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

The camera captures live frames from the environment. YOLO detects objects in each frame, then the program checks whether the obstacle is located on the left, right, or center of the image.
Based on the obstacle position and size, the system gives audio instructions such as moving left, moving right, slowing down, or continuing straight carefully.
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

* `smart_glasses_main.py`: main prototype code used for object detection, audio guidance, GPS reading, emergency button control, and Telegram location sharing
* `requirements.txt`: required Python libraries
* `.gitignore`: files ignored by Git 
* `images/`: project images and prototype photos

## Team Members

* Cynthia Issa
* Assil Sabbagh
* Fawzi Rabah
* Hala Al Tabech

## Status

This project was developed as an academic Raspberry Pi prototype. Full operation requires the Raspberry Pi hardware, camera, GPS module, push button, and audio output to be connected.

## Note

Private credentials such as Telegram bot tokens and chat IDs were removed from the public version for security.



