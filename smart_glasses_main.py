from ultralytics import YOLO
from picamera2 import Picamera2
import tensorflow as tf
import pyttsx3
import cv2
import time
import RPi.GPIO as GPIO
import serial
import requests

# ---------------- CONFIG ----------------

# Emergency push button (BCM numbering)
EMERGENCY_PIN = 17

# GPS module (NEO-7M)
GPS_SERIAL_PORT = "/dev/serial0"
GPS_BAUD = 9600

# Telegram bot settings
TELEGRAM_BOT_TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "PUT_YOUR_CHAT_ID_HERE"

# Obstacle thresholds
VERY_CLOSE_THRESH = 0.11
NORMAL_THRESH = 0.035

# Speech handling
COOLDOWN_SEC = 3.0
PATH_CLEAR_COOLDOWN = 10.0

print("Tensorflow version:", tf.__version__)

# ---------------- TEXT-TO-SPEECH ----------------

engine = pyttsx3.init()
engine.setProperty("rate", 175)
engine.setProperty("volume", 1.0)

def speak(text: str):
    print("SAY:", text)
    try:
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        print("TTS error:", e)

# ---------------- TELEGRAM + GPS ----------------

def send_telegram_location(lat, lon):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendLocation"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "latitude": float(lat),
        "longitude": float(lon),
        "horizontal_accuracy": 30
    }
    try:
        r = requests.post(url, json=data, timeout=10)
        print(f"Telegram status: {r.status_code}, response: {r.text}")
    except Exception as e:
        print("Error sending Telegram location:", e)

def _parse_lat_lon_from_nmea(nmea: str):
    if not nmea.startswith("$GPRMC") and not nmea.startswith("$GPGGA"):
        return None, None

    parts = nmea.split(",")
    if len(parts) < 7:
        return None, None

    try:
        # Latitude
        lat_raw = parts[3]
        lat_dir = parts[4]
        if lat_raw == "" or lat_dir == "":
            return None, None

        lat_deg = float(lat_raw[:2])
        lat_min = float(lat_raw[2:])
        lat = lat_deg + lat_min / 60.0
        if lat_dir == "S":
            lat = -lat

        # Longitude
        lon_raw = parts[5]
        lon_dir = parts[6]
        if lon_raw == "" or lon_dir == "":
            return None, None

        lon_deg = float(lon_raw[:3])
        lon_min = float(lon_raw[3:])
        lon = lon_deg + lon_min / 60.0
        if lon_dir == "W":
            lon = -lon

        return lat, lon

    except:
        return None, None

def get_gps_location(timeout=10.0):
    try:
        ser = serial.Serial(GPS_SERIAL_PORT, GPS_BAUD, timeout=1)
    except Exception as e:
        print("WARNING: Could not open GPS serial port:", e)
        return None, None

    start = time.time()
    lat = lon = None

    try:
        while time.time() - start < timeout:
            line = ser.readline().decode(errors="ignore").strip()
            if not line:
                continue

            lat, lon = _parse_lat_lon_from_nmea(line)
            if lat is not None and lon is not None:
                print("GPS fix:", lat, lon)
                break
    finally:
        ser.close()

    if lat is None or lon is None:
        print("GPS fix not obtained within timeout.")
    return lat, lon

# ---------------- CAMERA SETUP ----------------

picam2 = Picamera2()
picam2.preview_configuration.main.size = (320, 240)
picam2.preview_configuration.main.format = "XRGB8888"
picam2.preview_configuration.align()
picam2.configure("preview")
picam2.start()

# ---------------- YOLO MODEL ----------------

try:
    model = YOLO("yolo11n.pt")
    print("Loaded YOLO11n model successfully")
except Exception as e:
    print("Could not load yolol11n.pt, trying yolov8n instead:", e)
    model = YOLO("yolov8n.pt")

print("Smart glasses started. Press Ctrl+C in the terminal to stop.")

# ---------------- GPIO SETUP ----------------

GPIO.setmode(GPIO.BCM)
GPIO.setup(EMERGENCY_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

emergency_triggered = False
last_button_state = GPIO.input(EMERGENCY_PIN)

# ---------------- STATE VARIABLES ----------------

frame_id = 0
last_sentence = ""
last_spoken_time = 0.0
last_clear_time = 0.0

# ---------------- MAIN LOOP ----------------

try:
    while True:
        frame = picam2.capture_array()

        # Remove alpha if present
        if frame.ndim == 3 and frame.shape[2] == 4:
            frame = frame[:, :, :3]

        frame_id += 1
        now = time.time()

        # --- Emergency button logic ---
        button_state = GPIO.input(EMERGENCY_PIN)

        if last_button_state == GPIO.HIGH and button_state == GPIO.LOW:
            print("Emergency button pressed!")
            emergency_triggered = True

        last_button_state = button_state

        if emergency_triggered:
            emergency_triggered = False
            speak("Emergency button pressed. Getting your location.")
            lat, lon = get_gps_location(timeout=10.0)
            if lat is None or lon is None:
                speak("Sorry, GPS signal is not ready.")
            else:
                send_telegram_location(lat, lon)
                speak("Emergency location sent.")

        # Skip detection every other frame (speed)
        display_frame = frame
        if frame_id % 2 != 0:
            cv2.imshow("Pi YOLO Live", display_frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
            continue

        # -------- YOLO inference --------
        results = model(frame, imgsz=320, conf=0.30, verbose=False)
        boxes = results[0].boxes

        annotated_frame = results[0].plot()
        display_frame = cv2.cvtColor(annotated_frame, cv2.COLOR_RGB2BGR)

        cv2.imshow("Pi YOLO Live", display_frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

        h, w, _ = frame.shape
        sentence = None

        close_left = close_center = close_right = 0
        max_left_area = max_center_area = max_right_area = 0.0

        # Parse detections
        if len(boxes) > 0:
            xyxy = boxes.xyxy

            for j in range(len(xyxy)):
                x1, y1, x2, y2 = xyxy[j].tolist()
                box_w = x2 - x1
                box_h = y2 - y1
                area = box_w * box_h
                rel_area = area / float(w * h)

                if rel_area < NORMAL_THRESH:
                    continue

                center_x = (x1 + x2) / 2.0

                # Left side
                if center_x < w / 3.0:
                    close_left += 1
                    if area > max_left_area:
                        max_left_area = area

                # Right side
                elif center_x > 2 * w / 3.0:
                    close_right += 1
                    if area > max_right_area:
                        max_right_area = area

                # Center
                else:
                    close_center += 1
                    if area > max_center_area:
                        max_center_area = area

        rel_center_area = max_center_area / float(w * h) if max_center_area > 0 else 0.0
        rel_left_area = max_left_area / float(w * h) if max_left_area > 0 else 0.0
        rel_right_area = max_right_area / float(w * h) if max_right_area > 0 else 0.0

        center_blocked = rel_center_area > NORMAL_THRESH
        left_blocked = rel_left_area > NORMAL_THRESH
        right_blocked = rel_right_area > NORMAL_THRESH

        # -------- Navigation logic --------

        if center_blocked:
            if rel_center_area > VERY_CLOSE_THRESH:
                if not left_blocked and right_blocked:
                    sentence = "Obstacle very close ahead, move right."
                elif not right_blocked and left_blocked:
                    sentence = "Obstacle very close ahead, move left."
                else:
                    sentence = "Obstacle very close ahead, move left."
            else:
                if rel_left_area < rel_right_area:
                    sentence = "Obstacle ahead, move slightly right."
                else:
                    sentence = "Obstacle ahead, move slightly left."
        else:
            if left_blocked and not right_blocked:
                sentence = "Obstacle on your left, keep to the right."
            elif right_blocked and not left_blocked:
                sentence = "Obstacle on your right, keep to the left."
            elif left_blocked and right_blocked:
                sentence = "Obstacles on both sides, keep going straight carefully."
            else:
                if (now - last_clear_time) > PATH_CLEAR_COOLDOWN:
                    sentence = "Path seems clear ahead."
                    last_clear_time = now

        # -------- Output speech --------
        if sentence is not None:
            enough_time_passed = (now - last_spoken_time) > COOLDOWN_SEC
            changed_sentence = sentence != last_sentence

            if enough_time_passed and changed_sentence:
                speak(sentence)
                last_sentence = sentence
                last_spoken_time = now

except KeyboardInterrupt:
    print("\nStopping smart glasses program.")

finally:
    cv2.destroyAllWindows()
    picam2.stop()
    GPIO.cleanup()
    try:
        engine.stop()
    except:
        pass