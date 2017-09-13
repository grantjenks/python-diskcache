import random, requests, signal, time, threading

signal.signal(signal.SIGINT, lambda signum, frame: exit())


count = 0

def monitor():
    global count
    while True:
        time.sleep(1)
        print(f"{'*' * (count // 8)}")
        count = 0

thread = threading.Thread(target=monitor)
thread.daemon = True
thread.start()


while True:
    value = int(random.expovariate(1) * 100)
    response = requests.get(f'http://127.0.0.1:8000/echo/{value}')
    count += 1
