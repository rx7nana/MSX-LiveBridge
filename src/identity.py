EXTENSION_ID = "fcebnajmcgjhmkbgefjgaaadnjpdamnc"
STORE_EXTENSION_ID = "cfkcbmejlakciepflheboofnphdkoghf"
ALLOWED_EXTENSION_IDS = (EXTENSION_ID, STORE_EXTENSION_ID)
ALLOWED_EXTENSION_ORIGINS = tuple(f"chrome-extension://{value}" for value in ALLOWED_EXTENSION_IDS)
HOST_NAME = "com.msxlivebridge.connect"
APP_NAME = "MSX LiveBridge"
VERSION = "1.0.4"
