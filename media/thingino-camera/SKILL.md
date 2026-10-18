---
name: thingino-camera
description: Use when operating or probing a Thingino IP camera.
version: 0.1.0
author: Hermes Agent 01
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [thingino, camera, ip-camera, onvif, rtsp, iot, firmware]
    related_skills: []
    required_commands: [curl]
---

# Thingino camera (operate & configure)

Thingino is open firmware that turns Ingenic SoC IP cameras (Wyze, Atom, Aqara, and white-label T-series) into local Linux devices: RTSP/WebRTC streaming, ONVIF, a Bootstrap web UI, MQTT/Home Assistant, and motion alerts — no cloud.

## When to Use

Use when you need to reach, authenticate to, read, or change a live Thingino camera — probe what it can do, configure streams/ISP/motion/notifications, pull RTSP/snapshots, or drive actions (reboot, record, pan/tilt). Not for building or OTA-flashing firmware.

This skill is for operating/configuring a RUNNING camera, not building firmware. (Firmware build/OTA work lives in the community `themactep/thingino-skills` repo, which is dev-only.)

## Step 1 — Discover the API surface (JS is the source of truth)

Endpoints are not documented on the box. Pull the UI's JS and grep it:

```
curl -s http://IP/preview.html          # note the /a/*.js script tags
curl -s "http://IP/a/main.js" > main.js  # biggest bundle
# then: grep -oE '"/x/[a-z0-9-]+\.cgi"' main.js  and  grep -oE '"/[a-z0-9/_.-]+"' main.js
```

Endpoints are spread across MULTIPLE bundles — grep every `<script src>` from `/preview.html`, not just `main.js`. PTZ cameras load `preview-motors.js`, which carries the motor CGIs (`/x/json-motor.cgi`, `/x/json-motor-params.cgi`) that are absent from `main.js`. Detect PTZ via `runtime-config.js` → `thinginoUIConfig.device.motors === true`.

Key endpoints (present on stable): `/x/login.cgi`, `/x/session-status.cgi`, `/x/json-config-webui.cgi`, `/x/json-heartbeat.cgi` (+ `-slow`), `/x/json-imp.cgi`, `/x/json-prudynt.cgi`, `/x/json-send2.cgi`, `/x/json-wireguard.cgi`, `/x/reboot.cgi`, `/x/tool-record.cgi`, `/x/send.cgi`, `/x/run.cgi`, `/x/agent.cgi`, snapshots `/x/dl0.jpg` `/x/dl1.jpg`, MJPEG `/x/ch0.mjpg`.

Pitfall: the bare `/api/v1/*` paths and unknown paths return a 302-style HTML refresh to `/login.html` — an unauth redirect, not a 404. A 200 with a tiny `<meta refresh> to /` body means you hit an unauthenticated path, not a real endpoint.

## Step 2 — Authenticate (session cookie, NOT basic auth)

HTTP basic auth (`curl -u`) does NOT work — it returns `{"authenticated":false}` from session-status. The login is a JSON POST:

```
curl -s -c jar -b jar -X POST http://IP/x/login.cgi \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"<u>\",\"password\":\"<base64-of-plaintext>\",\"encoding\":\"base64\"}"
# -> {"success":true,"is_default_password":bool}
```

The password is base64 of the PLAINTEXT (not an already-hashed value); `encoding` always `"base64"`. The session cookie from this call governs every later request (`curl -b jar`).

Creds vary per camera — do not assume. The login form pre-fills `root`; RTSP/HTTP server defaults are `thingino/thingino`. Brute a short list (`root`/`thingino`/`admin` × empty/`root`/`thingino`/`admin`) rather than guessing once. A successful login with `is_default_password:false` just means a non-default password is set.

## Step 3 — Read config via the agent API (through the proxy)

The camera agent API is served only through a CGI proxy, never at its raw path:

```
curl -s -b jar "http://IP/x/agent.cgi?agent_path=/api/v1/config" -H 'Accept: application/json'
```

- `/api/v1/config` — full persisted config (the complete "what can be configured" answer).
- `/api/v1/capabilities` — bool map of which fields are settable.
- `/api/v1/device` — identity + firmware/streamer/API version.
- `/api/v1/runtime/*` — live state (motion, streams/N, media).

Pitfall: GET `/api/v1/config` DIRECTLY redirects to the login page even with a valid session — the `agent_path` query param is mandatory, and an `X-API-Key` header can substitute for the cookie where a key exists.

## Step 4 — Write / act

- Config writes + password change: POST `/x/json-config-webui.cgi` (JSON body).
- Per-subsystem CGI also accept write: `json-imp.cgi` (ISP), `json-prudynt.cgi` (streamer), `json-send2.cgi` (notifications).
- Actions: `/x/reboot.cgi`, `/x/tool-record.cgi` (clip), `/x/send.cgi`, `/x/run.cgi`.
- Media: RTSP `rtsp://thingino:thingino@ip/ch0` (and `ch1`); snapshot `/x/dl0.jpg` `/x/dl1.jpg`; MJPEG `/x/ch0.mjpg`.

## Step 5 — PTZ / motor control (pan/tilt cams only)

PTZ is NOT in the camera-agent API — it is a parallel legacy CGI pair, referenced only by `preview-motors.js`. `/api/v1/config` and `/api/v1/capabilities` carry no motor settings (capabilities just flips `ptz.enabled`). Motor config and motion live entirely here.

Read parameters (GET):

```
curl -s -b jar "http://IP/x/json-motor-params.cgi"
# -> {"steps_pan":4050,"steps_tilt":1000,"accel_pan":0,"accel_tilt":0,
#     "motion_driver":"legacy","preview_control_mode":"step",
#     "pos_0_x":2025,"pos_0_y":500}
```

Command (GET, query args on `/x/json-motor.cgi`):

- `d=j` — read position/status (safe): `{"code":200,"result":"success","message":{"status","xpos","ypos","speed","invert"}}`
- `d=g&x=<dx>&y=<dy>` — relative move (signed step offsets)
- `d=x&x=<x>&y=<y>` — absolute move to x/y (within steps_pan × steps_tilt)
- `d=r` — home/reset (recalibrate; the UI follows it with an absolute `d=x` back to pos_0)

The UI derives per-click step size as `steps_pan / 100` for x and `steps_tilt / 100` for y; `preview_control_mode` is `step` (per-click) or `continuous` (hold-to-move).

## Pitfalls (general)

- Grep the UI JS to discover endpoints; never guess CGI names — the JS bundle is the authority and changes across firmware versions.
- Don't use basic auth; the base64 JSON login POST is the only path to a session cookie.
- Always route agent API calls through `agent_path`; the raw `/api/v1` prefix is a redirect trap.
- The web UI also has its own non-camera prefs (`level`, `paranoid`, `theme`) returned by `json-config-webui.cgi` — don't confuse them with the camera config in `/api/v1/config`.
- Motor/PTZ endpoints exist only on pan/tilt cams and are NOT in the agent API — read them from `preview-motors.js`, not `main.js`.

See `references/config-surface.md` for the full config key map (image/motion/daynight/streams/OSD/audio/storage/send2 + motors/PTZ) and the capabilities contract.