#!/bin/bash
set -u

readonly FFMPEG=/usr/lib/ffmpeg/7.0/bin/ffmpeg
readonly FFPROBE=/usr/lib/ffmpeg/7.0/bin/ffprobe
readonly SOURCE_SECRET=/run/secrets/FRIGATE_STARLING_NEST_RTSP_URL
readonly DESTINATION=rtsp://nest-relay:8554/nest
readonly ARC_RENDER_DEVICE=/dev/dri/renderD128
readonly WATCH_INTERVAL=15
readonly WATCH_FAILURE_LIMIT=2

child_pid=
watchdog_pid=

if ! IFS= read -r source_url < "${SOURCE_SECRET}" || [[ -z "${source_url}" ]]; then
  echo "Nest source secret is missing or empty" >&2
  exit 1
fi

stop_children() {
  trap - TERM INT

  if [[ -n "${watchdog_pid}" ]]; then
    kill "${watchdog_pid}" 2>/dev/null || true
    wait "${watchdog_pid}" 2>/dev/null || true
  fi

  if [[ -n "${child_pid}" ]]; then
    kill -TERM "${child_pid}" 2>/dev/null || true
    wait "${child_pid}" 2>/dev/null || true
  fi

  exit 0
}

watch_output() {
  local transcoder_pid=$1
  local failures=0

  while kill -0 "${transcoder_pid}" 2>/dev/null; do
    sleep "${WATCH_INTERVAL}"
    kill -0 "${transcoder_pid}" 2>/dev/null || return

    if timeout --signal=TERM 8 "${FFPROBE}" \
      -v error \
      -rtsp_transport tcp \
      -timeout 5000000 \
      -read_intervals "%+1" \
      -select_streams v:0 \
      -show_entries packet=pts_time \
      -of csv=p=0 \
      "${DESTINATION}" >/dev/null 2>&1; then
      failures=0
      continue
    fi

    failures=$((failures + 1))
    echo "Nest relay output probe failed (${failures}/${WATCH_FAILURE_LIMIT})" >&2

    if (( failures >= WATCH_FAILURE_LIMIT )); then
      echo "Nest relay output is stalled; terminating the transcoder" >&2
      kill -TERM "${transcoder_pid}" 2>/dev/null || true
      return
    fi
  done
}

trap stop_children TERM INT

while true; do
  nice -n 10 "${FFMPEG}" \
    -hide_banner \
    -loglevel warning \
    -init_hw_device "qsv=arc:${ARC_RENDER_DEVICE}" \
    -filter_hw_device arc \
    -rtsp_transport tcp \
    -timeout 10000000 \
    -fflags +genpts+discardcorrupt \
    -use_wallclock_as_timestamps 1 \
    -hwaccel qsv \
    -hwaccel_device arc \
    -hwaccel_output_format qsv \
    -i "${source_url}" \
    -map 0:v:0 \
    -map 0:a:0? \
    -c:v h264_qsv \
    -preset veryfast \
    -low_power 1 \
    -profile:v high \
    -level:v 4.1 \
    -b:v 1800k \
    -maxrate:v 3M \
    -bufsize:v 6M \
    -g 30 \
    -forced_idr 1 \
    -repeat_pps 1 \
    -scenario videosurveillance \
    -bf 0 \
    -r 15 \
    -fps_mode cfr \
    -af aresample=async=1:first_pts=0 \
    -c:a aac \
    -b:a 64k \
    -muxdelay 0.1 \
    -f rtsp \
    -rtsp_transport tcp \
    "${DESTINATION}" &

  child_pid=$!
  watch_output "${child_pid}" &
  watchdog_pid=$!

  wait "${child_pid}"
  exit_code=$?
  child_pid=

  kill "${watchdog_pid}" 2>/dev/null || true
  wait "${watchdog_pid}" 2>/dev/null || true
  watchdog_pid=

  echo "Nest transcoder exited with status ${exit_code}; retrying in 2 seconds" >&2
  sleep 2
done
