from time import time, sleep
from diskcache import FanoutCache

# Initialise the maximum delay reference
max_delay = 0

# Initialise the reference to current time
# Add a significant amount of time to ignore the first measurement due to other initialisations
current_time = time() + 100

# Initialise the Fanout Cache instance
data = FanoutCache('test', shards=8)


# Declare the function used to modify the data
def set_data(**kwargs):
    """

    Function used to modify the cache.

    :param kwargs: Key, value pairs of data to modify.

    """

    # Fetch the global variables
    global max_delay
    global current_time
    global data

    # Update the data with the given keyword arguments
    for key, value in kwargs.items():

        # Measure the time taken to update it for each item
        temp = time()
        dif = temp - current_time
        if dif > max_delay:
            max_delay = dif
            print("New max delay encountered: ", max_delay)
        current_time = temp

        # Update the data
        data[key] = value


# Initialise some test values
test_values = {str(key): value for key in range(25) for value in range(25)}

# Keep writing the data in 0.1 sec intervals
while True:
    sleep(0.1)
    set_data(**test_values)
