"""Constants for Bosch eBike integration."""

DOMAIN = "ha_bosch_ebike"

AUTH_BASE_URL = "https://p9.authz.bosch.com/auth/realms/obc/protocol/openid-connect"
AUTH_URL = f"{AUTH_BASE_URL}/auth"
TOKEN_URL = f"{AUTH_BASE_URL}/token"
API_BASE_PROFILE_URL = "https://obc-rider-profile.prod.connected-biking.cloud"
API_BASE_ACTIVITY_URL = "https://obc-rider-activity.prod.connected-biking.cloud"

BIKES_ENDPOINT = "/v2/bike-profile"
ACTIVITIES_ENDPOINT = "/v1/activity"
BIKE_PASS_ENDPOINT = "/bike-pass/smart-system/v1/bike-passes"
SERVICE_RECORDS_ENDPOINT = "/service-book/smart-system/v1/service-records"

DEFAULT_SCAN_INTERVAL = 30  # minutes
DEFAULT_BATTERY_CAPACITY_WH = 750  # Default battery capacity in Wh

# Service / maintenance reminder thresholds
SERVICE_WARN_DAYS = 30
SERVICE_WARN_KM = 200

# Event names
EVENT_SERVICE_DUE_SOON = f"{DOMAIN}_service_due_soon"
EVENT_SERVICE_OVERDUE = f"{DOMAIN}_service_overdue"
EVENT_MAINTENANCE_DUE_SOON = f"{DOMAIN}_maintenance_due_soon"
EVENT_MAINTENANCE_OVERDUE = f"{DOMAIN}_maintenance_overdue"

REDIRECT_URI = "onebikeapp-android://com.bosch.ebike.onebikeapp/oauth2redirect"

# Bosch Data Act developer portal where the user registers an "app" to get a
# Client-ID and must ACTIVATE it before the OAuth login works.
FLOW_PORTAL_URL = "https://portal.bosch-ebike.com/data-act/app"

# OAuth2 scope requested during authorization.
OAUTH_SCOPE = "openid"

CONF_CLIENT_ID = "client_id"

# Optional links to live BLE sensors (provided by the ESPHome bridge in
# `esphome/components/bosch_ebike_ldi/`). When configured, the integration
# uses recorder history of these sensors at tour start/end to compute exact
# distance and consumption — overriding the cloud-derived values.
CONF_LIVE_ODOMETER_ENTITY = "live_odometer_entity"
CONF_LIVE_SOC_ENTITY = "live_soc_entity"
