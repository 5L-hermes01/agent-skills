# Thingino camera config surface (api/v1/config + capabilities)

Condensed key map extracted from a stable Wyze Cam 2 (T20 SoC) build. Field paths are relative to `/api/v1/config` (high-level) or `backend.raw` (prudynt native). `/api/v1/capabilities` marks which are settable.

## Top-level config
- `image` — brightness(128), contrast(128), saturation(128), sharpness(128), anti_flicker(2), hflip, vflip.
- `motion` — enabled.
- `daynight` — enabled, force_mode(auto|day|night|null).
- `privacy` — enabled, channel(all).
- `storage` — autostart, channel, device_path(%hostname), duration(60), filename(%Y/%m/%d/%H-%M-%S), mount.
- `streams[]` — id, enabled, audio_enabled, width, height, fps, bitrate, format(H264), mode(CBR).
- `backend` — name(prudynt) + `raw` (full native config below).

## backend.raw (prudynt native), by section

### image (ISP — deeper than top-level)
ae_compensation, backlight_compensation, core_wb_mode, defog_strength, dpc_strength, drc_strength, hue, highlight_depress, isp_bypass, running_mode, max_again, max_dgain, wb_rgain, wb_bgain, brightness/contrast/saturation/sharpness, anti_flicker, hflip/vflip.

### daynight (deep)
enabled, controls{binswitch,color,ir850,ir940,ircut,white}, schedule{enabled,start_at,stop_at}, switch_above_percent(80), switch_below_percent(15), tolerance_percent(50), total_gain_day_threshold(300), total_gain_night_threshold(3000), gb_gain_absolute(145), gb_gain_delta(15), ev_day_low_primary/secondary, ev_night_high, sample_interval_ms, settle_samples_for_gb_record, day/night_count_threshold, script_path(/sbin/daynight).

### motion (deep)
enabled, sensitivity(1), init_time(5), min_time(1), cooldown_time(5), debounce_time, post_time, video_length(10), monitor_stream(1), skip_frame_count(5), roi_count/roi_0_x/y/roi_1_x/y, frame_width/height, ivs_polling_timeout, motor_settle_ms, playonspeaker, send2{email,ftp,gotify,mqtt,ntfy,storage,telegram,webhook} (booleans), script_path(/usr/sbin/motion).

### audio
mic{enabled, gain(25), vol(80), bitrate(32), sample_rate(16000), format(AAC), agc_enabled, agc_target_level_dbfs, agc_compression_gain_db, alc_gain, noise_suppression, high_pass_filter, is_digital}, spk{enabled, gain(20), vol(80), sample_rate}, force_stereo, tap_enabled, tap_path, buffer_cap_frames, buffer_warn_frames.

### stream0 / stream1 (encoders)
enabled, video_enabled, audio_enabled, width, height, fps, bitrate, mode(CBR), format(H264), gop(30), max_gop(60), qp_init/min/max, profile(2), rotation, ip_delta/pb_delta, allow_shared, rtsp_endpoint(ch0|ch1), rtsp_info, scale_enabled/scale_width/height, plus `osd` (below).

### osd (per stream)
enabled, font_path, font_size, start_delay, stroke_size. Overlays each {enabled, format, position, rotation, fill_color, stroke_color}: time(timestamp), uptime, usertext(%hostname), logo(path/width/height/transparency), brightness, privacy(text/layer/opacity — the red PRIVACY ENABLED band).

### stream2 / stream3 (JPEG snapshots)
enabled, fps(15), jpeg_channel(0|1), jpeg_idle_fps(1), jpeg_quality(75), jpeg_path(/tmp/snapshot.jpg|snapshot_ch1.jpg).

### http / rtsp (servers)
http: enabled, port(8080), auth_required, username/password(thingino), mjpeg_enabled, api_enabled.
rtsp: enabled via port(554), auth_required, username/password(thingino), est_bitrate, bandwidth_margin, out_buffer_size, send_buffer_size, session_reclaim, packet_loss_threshold, audio_only_enabled/endpoint(mic).

### recorder
mirrors top-level storage (autostart, channel, device_path, duration, filename, mount).

### sensor
i2c_bus, mclk, boot, fps, gpio_reset, video_interface.

## capabilities (what the backend advertises as settable)
- image, motion{sensitivity,cooldown_time}, daynight(modes), privacy, storage, streams{count,snapshot,clip_recording}, services.streaming{start,stop,restart}.
- send2: email, ftp, gphotos, mqtt, ntfy, storage, telegram, webhook — each {enabled, send_photo, send_video}.
- ptz.enabled (false on fixed cams), firmware.upgrade (OTA available).

## Device identity (`/api/v1/device`)
id, name, hostname, manufacturer(Thingino), model(<brand>_<model>_<soc>_<sensor>_<wifi>), software{firmware_version, api_version("0-local" on older builds), streamer}, backend{name, available}.

## Runtime (`/api/v1/runtime/*`)
motion{enabled,active}; streams/N{width,height,fps,bitrate,format,mode,rtsp_endpoint,rtsp_url,rtsp_listener_up,recording_active,healthy}; media{streams{ch0/ch1{available,enabled,snapshot_url(/x/dl0.jpg,/x/dl1.jpg)}}}.

## Motors / PTZ (pan/tilt cams only — NOT in the agent API)

Motor control is a parallel legacy CGI pair referenced only by `preview-motors.js`; it is absent from `/api/v1/config` and `/api/v1/capabilities` (which flips only `ptz.enabled`). Present only when `thinginoUIConfig.device.motors === true`.

- `/x/json-motor-params.cgi` (GET) → `steps_pan`, `steps_tilt` (traverse range in steps), `accel_pan`, `accel_tilt`, `motion_driver` ("legacy"), `preview_control_mode` ("step"|"continuous"), `pos_0_x`, `pos_0_y` (home/origin coords). Seen on a Wuuk Y0510: steps_pan 4050, steps_tilt 1000.
- `/x/json-motor.cgi` (GET, query args) → JSON `{code,result,message}`:
  - `d=j` — read position/status (message.status/xpos/ypos/speed/invert).
  - `d=g&x=&y=` — relative move (signed step offsets).
  - `d=x&x=&y=` — absolute move within the step range.
  - `d=r` — home/reset (recalibrate).

Per-click step = `steps_pan/100` (x) and `steps_tilt/100` (y). No motor config lives under `/api/v1/config`; the fixed-camera and PTZ config payloads are byte-identical apart from `motion.motor_settle_ms`.
