from ultralytics import YOLO
from picamera2 import Picamera2
import tensorflow as tf
import pyttsx3
import cv2
import time
import RPi.GPIO as GPIO
import serial
import requests
import threading
import queue

# ---------------- CONFIG ----------------

# Emergency push button (BCM numbering)
EMERGENCY_PIN = 17

# GPS module (NEO-7M)
GPS_SERIAL_PORT = "/dev/serial0"
GPS_BAUD = 9600

# Telegram bot settings  ? PUT YOUR OWN VALUES HERE, DON'T HARD-CODE REAL TOKENS IN PUBLIC CODE
TELEGRAM_BOT_TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "PUT_YOUR_CHAT_ID_HERE"

# Obstacle thresholds
VERY_CLOSE_THRESH = 0.11
NORMAL_THRESH = 0.035

# Speech handling
COOLDOWN_SEC = 3.0
PATH_CLEAR_COOLDOWN = 10.0

# Detection throttling
SKIP_DET_FRAMES = 2   # run YOLO every Nth frame (2 = every 2nd, 3 = every 3rd)

print("Tensorflow version:", tf.__version__)

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
    except Exception:
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

# ---------------- TTS THREAD ----------------

def tts_worker(speak_queue: queue.Queue, stop_event: threading.Event):
    """
    Runs in its own thread. Consumes sentences from the queue and
    uses pyttsx3 to speak them. This keeps TTS from blocking YOLO/camera.
    """
    engine = pyttsx3.init()
    engine.setProperty("rate", 175)
    engine.setProperty("volume", 1.0)

    while not stop_event.is_set():
        try:
            # Wait for up to 0.5s for a new sentence
            sentence = speak_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        if sentence is None:
            # Sentinel to stop the thread
            break

        print("SAY:", sentence)
        try:
            engine.say(sentence)
            engine.runAndWait()
        except Exception as e:
            print("TTS error:", e)

try:
     engine.stop()
except Exception:
        pass

# ---------------- CAMERA SETUP ----------------

picam2 = Picamera2()
video_config = picam2.create_video_configuration(
    main={"size": (320, 240), "format": "RGB888"},
    buffer_count=2,
)
picam2.configure(video_config)
picam2.start()

# ---------------- YOLO MODEL ----------------

try:
    model = YOLO("yolov11n.pt")
    print("Loaded YOLO11n model successfully")
except Exception as e:
    print("Could not load yolo11n.pt, trying yolov8n instead:", e)
    model = YOLO("yolov8n.pt")
    print("Loaded YOLOv8n model")

print("Smart glasses started with threading. Press Ctrl+C in the terminal to stop.")

# ---------------- GPIO SETUP ----------------

GPIO.setmode(GPIO.BCM)
GPIO.setup(EMERGENCY_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
last_button_state = GPIO.input(EMERGENCY_PIN)

# ---------------- SHARED STATE ----------------

latest_frame = None        # last raw frame from camera
display_frame = None       # frame to show in imshow (annotated or raw)
frame_lock = threading.Lock()

frame_id = 0
last_sentence = ""
last_spoken_time = 0.0
last_clear_time = 0.0

running = True

speak_queue = queue.Queue()
tts_stop_event = threading.Event()

# ---------------- THREAD: CAMERA CAPTURE ----------------

def capture_loop():
    global latest_frame, frame_id, display_frame, running

    while running:
        frame = picam2.capture_array()

        # Just in case: ensure 3 channels (RGB)
        if frame.ndim == 3 and frame.shape[2] > 3:
            frame = frame[:, :, :3]

        with frame_lock:
            latest_frame = frame
            # If no display frame yet, show raw
            if display_frame is None:
                display_frame = frame

        frame_id += 1
        # tiny sleep to yield CPU
        time.sleep(0.001)

# ---------------- THREAD: YOLO DETECTION + NAVIGATION ----------------

def detection_loop():
    global display_frame, last_sentence, last_spoken_time, last_clear_time, running

    while running:
        # Get a snapshot of the latest frame
        with frame_lock:
            frame = None if latest_frame is None else latest_frame.copy()

        if frame is None:
            time.sleep(0.01)
            continue

        # Throttle YOLO
        current_frame_id = frame_id
        if current_frame_id % SKIP_DET_FRAMES != 0:
            time.sleep(0.005)
            continue

 # -------- YOLO inference --------
        try:
            results = model(frame, imgsz=320, conf=0.30, verbose=False)
        except Exception as e:
            print("YOLO error:", e)
            time.sleep(0.05)
            continue

        boxes = results[0].boxes
        annotated = results[0].plot()  # RGB

        # Update display frame (convert to BGR for imshow)
        bgr_annotated = cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR)
        with frame_lock:
            display_frame = bgr_annotated

        h, w, _ = frame.shape
        now = time.time()
        sentence = None

        # --- Obstacle aggregation (left/center/right) ---
        max_left_area = max_center_area = max_right_area = 0.0

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

                if center_x < w / 3.0:
                    if area > max_left_area:
                        max_left_area = area
                elif center_x > 2 * w / 3.0:
                    if area > max_right_area:
                        max_right_area = area
                else:
                    if area > max_center_area:
                        max_center_area = area

        rel_center_area = max_center_area / float(w * h) if max_center_area > 0 else 0.0
        rel_left_area   = max_left_area   / float(w * h) if max_left_area   > 0 else 0.0
        rel_right_area  = max_right_area  / float(w * h) if max_right_area  > 0 else 0.0

        center_blocked = rel_center_area > NORMAL_THRESH
        left_blocked   = rel_left_area   > NORMAL_THRESH
        right_blocked  = rel_right_area  > NORMAL_THRESH

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

        # -------- Speech scheduling (non-blocking) --------
        if sentence is not None:
            enough_time_passed = (now - last_spoken_time) > COOLDOWN_SEC
            changed_sentence = sentence != last_sentence

            if enough_time_passed and changed_sentence:
                speak_queue.put(sentence)
                last_sentence = sentence
                last_spoken_time = now

        time.sleep(0.005)
# ---------------- MAIN LOOP (GUI + EMERGENCY BUTTON) ----------------

# Start worker threads
capture_thread = threading.Thread(target=capture_loop, daemon=True)
detect_thread = threading.Thread(target=detection_loop, daemon=True)
tts_thread = threading.Thread(target=tts_worker, args=(speak_queue, tts_stop_event), daemon=True)

capture_thread.start()
detect_thread.start()
tts_thread.start()

try:

    emergency_triggered = False

    while True:
        # --- Show camera / annotated view ---
        with frame_lock:
            frame_to_show = None if display_frame is None else display_frame.copy()

        if frame_to_show is not None:
            cv2.imshow("Pi YOLO Live", frame_to_show)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

        # --- Emergency button logic ---
        button_state = GPIO.input(EMERGENCY_PIN)
        if last_button_state == GPIO.HIGH and button_state == GPIO.LOW:
            print("Emergency button pressed!")
            emergency_triggered = True
        last_button_state = button_state
        if emergency_triggered:
            emergency_triggered = False
            speak_queue.put("Emergency button pressed. Getting your location.")

            lat, lon = get_gps_location(timeout=10.0)
            if lat is None or lon is None:
                speak_queue.put("Sorry, GPS signal is not ready.")
            else:
                send_telegram_location(lat, lon)
                speak_queue.put("Emergency location sent.")

        time.sleep(0.01)
except KeyboardInterrupt:
    print("\nStopping smart glasses program.")

finally:
    running = False
    tts_stop_event.set()
    speak_queue.put(None)  # sentinel for TTS

    cv2.destroyAllWindows()
    picam2.stop()
    GPIO.cleanup()
