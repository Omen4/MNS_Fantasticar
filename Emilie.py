import pika
import RPi.GPIO as GPIO
import time
import mfrc522
import threading
import base64
import requests
#import psycopg2
from picamera import PiCamera
from time import sleep

# Disable pesky GPIO warnings
GPIO.setwarnings(False)

# Set GPIO mode
GPIO.setmode(GPIO.BCM)

# Define GPIO pins for the LED
motor_led_pin_green = 5
motor_led_pin_red = 6

# Define GPIO pins for Motor 1
in1_motor1 = 24
in2_motor1 = 23
en_motor1 = 16

# Define GPIO pins for Motor 2
in1_motor2 = 17
in2_motor2 = 27
en_motor2 = 22

# Define GPIO pins
Trig = 19
Echo = 26

# Setup for sonar detector
GPIO.setup(Trig, GPIO.OUT)
GPIO.setup(Echo, GPIO.IN)
GPIO.output(Trig, False)

# Setup for Motor 1
GPIO.setup(in1_motor1, GPIO.OUT)
GPIO.setup(in2_motor1, GPIO.OUT)
GPIO.setup(en_motor1, GPIO.OUT)
GPIO.output(in1_motor1, GPIO.LOW)
GPIO.output(in2_motor1, GPIO.LOW)
p_motor1 = GPIO.PWM(en_motor1, 1000)
p_motor1.start(50)

# Setup for Motor 2
GPIO.setup(in1_motor2, GPIO.OUT)
GPIO.setup(in2_motor2, GPIO.OUT)
GPIO.setup(en_motor2, GPIO.OUT)
GPIO.output(in1_motor2, GPIO.LOW)
GPIO.output(in2_motor2, GPIO.LOW)
p_motor2 = GPIO.PWM(en_motor2, 1000)
p_motor2.start(50)

# Set up GPIO pin as an output for the LED and start it as red = inactive
GPIO.setup(motor_led_pin_green, GPIO.OUT)
GPIO.setup(motor_led_pin_red, GPIO.OUT)
GPIO.output(motor_led_pin_red, GPIO.HIGH)
GPIO.output(motor_led_pin_green, GPIO.LOW)

# RabbitMQ connection parameters
rabbitmq_host = 'backend.groupe2.learn-it.ovh'
queue_names = ['backward', 'forward', 'left', 'right', 'start_engine']
ultrasonic_queue_name = 'obstacle'
rfid_queue_name = 'rfid'
credentials = pika.PlainCredentials('raspberry1', 'FHup472sWg9bC4')

# Initialize the RFID reader
MIFAREReader = mfrc522.MFRC522()

# Flag to determine if the engine is started
engine_started = False

# Flag to determine if an obstacle is detected
obstacle_detected = False

# Setup for img to send
file_name = "./img_to_send.jpg"

def message_callback(channel, method, properties, body):
    global engine_started, obstacle_detected    # Use a global variable to track engine status
    channel_name = method.routing_key
    print(f"Received message on channel '{channel_name}'")

    # Define if vehicle can move or not
    if not engine_started and channel_name != 'start_engine':
        print("Engine is not started. Cannot perform actions.")
        return
    
    if obstacle_detected and channel_name == 'forward':
        print("Obstacle detected. Cannot move forward.")
        return

    if channel_name == 'start_engine':
        print("Engine started or stopped!")
        engine_started = not engine_started
        if engine_started:
            # Led to green = active
            GPIO.output(motor_led_pin_green, GPIO.HIGH)
            GPIO.output(motor_led_pin_red, GPIO.LOW)
        elif not engine_started:
            # Led to red = inactive
            GPIO.output(motor_led_pin_red, GPIO.HIGH)
            GPIO.output(motor_led_pin_green, GPIO.LOW)
    elif channel_name == 'backward':
        move('backward', 0.5)
    elif channel_name == 'forward':
        move('forward', 0.5)
    elif channel_name == 'left':
        move('left', 0.5)
    elif channel_name == 'right':
        move('right', 0.5)

# Function to read distance from ultrasonic sensor and set the obstacle_detected flag
def check_ultrasonic_sensor():
    global obstacle_detected
    try:
        while True:
            time.sleep(1)  # Wait for 1 second before the next measurement

            GPIO.output(Trig, True)
            time.sleep(0.00001)
            GPIO.output(Trig, False)

            start_time = time.time()
            end_time = time.time()

            while GPIO.input(Echo) == 0:
                start_time = time.time()

            while GPIO.input(Echo) == 1:
                end_time = time.time()

            distance = round((end_time - start_time) * 340 * 100 / 2, 1)

            print("Distance: {} cm".format(distance))

            if distance < 20:  # Less than 20 cm
                print("Object detected within 20cm.")
                obstacle_detected = True
                # Publish a message on the 'obstacle' channel
                sending_channel.basic_publish(exchange='', routing_key='obstacle', body='Obstacle detected')
            else:
                obstacle_detected = False

    except KeyboardInterrupt:
        GPIO.cleanup()

# Function to read RFID cards and send to the 'rfid' queue
def read_rfid_and_send_to_queue():
    try:
        while True:
            # Scan for cards
            (status, TagType) = MIFAREReader.MFRC522_Request(MIFAREReader.PICC_REQIDL)

            # Get the UID of the card
            (status, uid) = MIFAREReader.MFRC522_Anticoll()

            # If we have the UID, continue
            if status == MIFAREReader.MI_OK:
                # Print UID
                print("UID: " + str(uid[0]) + "," + str(uid[1]) + "," + str(uid[2]) + "," + str(uid[3]))

                # Convert UID to a string and publish it to the 'rfid' queue
                rfid_data = ",".join(str(val) for val in uid)
                sending_channel.basic_publish(exchange='', routing_key=rfid_queue_name, body=rfid_data)
                print("NICOLAS ECOUTE MOI")
                time.sleep(2)

    except KeyboardInterrupt:
        GPIO.cleanup()

def capture_and_send_images():
    camera = PiCamera()
    camera.resolution = (1280, 720)
    camera.vflip = True
    camera.contrast = 10

    while True:
        time.sleep(1)

        # Taking picture
        camera.capture(file_name)

        # Converting picture to base64
        with open(file_name, 'rb') as image_file:
            base64_bytes = base64.b64encode(image_file.read())

        # Sending post request containing picture
        url = 'https://backend.groupe2.learn-it.ovh/api/images/upload'
        params = {'file': base64_bytes}
        x = requests.post(url, json=params)
        print(x)
        
#def insert_image_into_database(image_data):
    # Establish a database connection
 #   try:
  #      conn = psycopg2.connect(**db_params)
  #  except psycopg2.Error as e:
  #      print(f"Error: Unable to connect to the database: {e}")
  #      return

    # Create a cursor object to execute SQL queries
  #  try:
  #      cursor = conn.cursor()
  #  except psycopg2.Error as e:
  #      print(f"Error: Unable to create a database cursor: {e}")
  #      conn.close()
  #      return

    # Insert the image data into a PostgreSQL table
  #  try:
  #      cursor.execute("INSERT INTO your_table_name (image_column_name) VALUES (%s);", (psycopg2.Binary(image_data),))
  #      conn.commit()
  #      print("Image inserted into the database.")
  #  except psycopg2.Error as e:
  #      conn.rollback()  # Rollback the transaction in case of an error
  #      print(f"Error: Unable to insert image into the database: {e}")

    # Close the cursor and database connection
  # cursor.close()
  #  conn.close()
        
def start_image_thread():
    image_thread = threading.Thread(target=capture_and_send_images)
    image_thread.daemon = True
    image_thread.start()


# Move, send instructions to motors
# direction: forward, backward, right, left
def move(direction, duration=0):
    print('move')
    if direction == 'forward':
        print("forward")
        GPIO.output(in1_motor1, GPIO.LOW)
        GPIO.output(in2_motor1, GPIO.HIGH)

        GPIO.output(in1_motor2, GPIO.HIGH)
        GPIO.output(in2_motor2, GPIO.LOW)

    elif direction == 'backward':
        print("backward")
        GPIO.output(in1_motor1, GPIO.HIGH)
        GPIO.output(in2_motor1, GPIO.LOW)

        GPIO.output(in1_motor2, GPIO.LOW)
        GPIO.output(in2_motor2, GPIO.HIGH)

    elif direction == 'right':
        print("right")
        GPIO.output(in1_motor1, GPIO.HIGH)
        GPIO.output(in2_motor1, GPIO.LOW)

        GPIO.output(in1_motor2, GPIO.HIGH)
        GPIO.output(in2_motor2, GPIO.LOW)

    elif direction == 'left':
        print("left")
        GPIO.output(in1_motor1, GPIO.LOW)
        GPIO.output(in2_motor1, GPIO.HIGH)

        GPIO.output(in1_motor2, GPIO.LOW)
        GPIO.output(in2_motor2, GPIO.HIGH)
    sleep(duration)
    print("stop")
    GPIO.output(in1_motor1, GPIO.LOW)
    GPIO.output(in2_motor1, GPIO.LOW)
    print("Motor 1: stopped")
    GPIO.output(in1_motor2, GPIO.LOW)
    GPIO.output(in2_motor2, GPIO.LOW)
    print("Motor 2: stopped")

# Establish a connection to RabbitMQ server for listening
listening_connection = pika.BlockingConnection(
    pika.ConnectionParameters(
        host=rabbitmq_host,
        credentials=credentials
    )
)
listening_channel = listening_connection.channel()

# Declare and bind queues for all channels
for queue_name in queue_names:
    listening_channel.queue_declare(queue=queue_name, durable=True)
    listening_channel.basic_consume(queue=queue_name, on_message_callback=message_callback, auto_ack=True)

# Establish a connection to RabbitMQ server for sending
sending_connection = pika.BlockingConnection(
    pika.ConnectionParameters(
        host=rabbitmq_host,
        credentials=credentials
    )
)
sending_channel = sending_connection.channel()

# Declare and bind the 'rfid' queue
sending_channel.queue_declare(queue=rfid_queue_name, durable=True)

# Create a separate thread for the ultrasonic sensor
ultrasonic_thread = threading.Thread(target=check_ultrasonic_sensor)
ultrasonic_thread.daemon = True
ultrasonic_thread.start()

try:
    print("Waiting for messages. To exit, press Ctrl+C")

    # Separate thread for RFID card reading and publishing to the 'rfid' queue
    rfid_thread = threading.Thread(target=read_rfid_and_send_to_queue)
    rfid_thread.daemon = True
    rfid_thread.start()
    
    # Separate thread for capturing and sending images
    start_image_thread()

    # Continuously listen for messages from the server and control the car
    listening_channel.start_consuming()

# Added error cases for debug and consuming closing method
except KeyboardInterrupt:
    print("Received keyboard interrupt. Exiting...")
except pika.exceptions.AMQPError as amqp_error:
    print(f"An AMQP error occurred: {amqp_error}")
except Exception as e:
    print(f"An error occurred: {str(e)}")
finally:
    if listening_connection.is_open:
        try:
            listening_connection.close()
        except Exception as e:
            print(f"Error closing the listening connection: {str(e)}")
    if sending_connection.is_open:
        try:
            sending_connection.close()
        except Exception as e:
            print(f"Error closing the sending connection: {str(e)}")
    GPIO.cleanup()  # Clean up GPIO pins
