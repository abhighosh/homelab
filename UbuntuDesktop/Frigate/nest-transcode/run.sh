#!/bin/bash
set -u

readonly FFMPEG=/usr/lib/ffmpeg/7.0/bin/ffmpeg
readonly FFPROBE=/usr/lib/ffmpeg/7.0/bin/ffprobe
readonly GST_LAUNCH=/usr/bin/gst-launch-1.0
readonly SOURCE_SECRET=/run/secrets/FRIGATE_STARLING_NEST_RTSP_URL
readonly DESTINATION=rtsp://nest-relay:8554/nest
readonly ARC_RENDER_DEVICE=/dev/dri/renderD128
readonly TIMESTAMP_FONT=/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf
readonly WATCH_INTERVAL=15
readonly WATCH_FAILURE_LIMIT=2

source_pid=
child_pid=
watchdog_pid=

runtime_dir=$(mktemp -d /tmp/nest-transcoder.XXXXXX)
readonly runtime_dir
readonly clean_av_fifo=${runtime_dir}/clean-av.mkv
mkfifo "${clean_av_fifo}"

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

  if [[ -n "${source_pid}" ]]; then
    kill -TERM "${source_pid}" 2>/dev/null || true
  fi

  if [[ -n "${child_pid}" ]]; then
    kill -TERM "${child_pid}" 2>/dev/null || true
  fi

  if [[ -n "${source_pid}" ]]; then
    wait "${source_pid}" 2>/dev/null || true
  fi

  if [[ -n "${child_pid}" ]]; then
    wait "${child_pid}" 2>/dev/null || true
  fi

  rm -f "${clean_av_fifo}"
  rmdir "${runtime_dir}" 2>/dev/null || true

  exit 0
}

watch_output() {
  local transcoder_pid=$1
  local clean_source_pid=$2
  local failures=0

  while kill -0 "${transcoder_pid}" 2>/dev/null && kill -0 "${clean_source_pid}" 2>/dev/null; do
    sleep "${WATCH_INTERVAL}"
    kill -0 "${transcoder_pid}" 2>/dev/null || return
    kill -0 "${clean_source_pid}" 2>/dev/null || return

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
      echo "Nest relay output is stalled; terminating the clean decoder and transcoder" >&2
      kill -TERM "${clean_source_pid}" 2>/dev/null || true
      kill -TERM "${transcoder_pid}" 2>/dev/null || true
      return
    fi
  done
}

trap stop_children TERM INT

while true; do
  # FFmpeg's CLI logs corrupt decoded H.264 frames but still passes its
  # concealed pixels to filters. GStreamer's libav decoder can discard those
  # frames explicitly. videorate fills the resulting gaps with the previous
  # clean frame and Matroska carries raw A/V locally without another codec.
  "${GST_LAUNCH}" -q -e \
    rtspsrc location="${source_url}" protocols=tcp latency=200 drop-on-latency=true name=src \
    matroskamux name=mux streamable=true offset-to-zero=true ! \
      fdsink fd=1 sync=false \
    src. ! "application/x-rtp,media=video,encoding-name=H264" ! \
      queue ! rtph264depay ! h264parse ! \
      avdec_h264 discard-corrupted-frames=true ! \
      videorate ! "video/x-raw,format=I420,framerate=15/1" ! \
      queue ! mux. \
    src. ! "application/x-rtp,media=audio" ! \
      queue ! decodebin ! audioconvert ! audioresample ! \
      "audio/x-raw,format=S16LE,layout=interleaved,rate=48000,channels=2" ! \
      queue ! mux. >"${clean_av_fifo}" &

  source_pid=$!

  # The only CPU video work is Starling's 1080p15 H.264 decode. Frames are
  # immediately uploaded to the Arc; QSV retains the expensive encode stage.
  nice -n 10 "${FFMPEG}" \
    -hide_banner \
    -loglevel warning \
    -init_hw_device "qsv=arc:${ARC_RENDER_DEVICE}" \
    -filter_hw_device arc \
    -fflags +genpts+discardcorrupt \
    -i "${clean_av_fifo}" \
    -map 0:v:0 \
    -map 0:a:0? \
    -vf "drawtext=fontfile=${TIMESTAMP_FONT}:text='%{localtime\\:%F %T}':x=8:y=6:fontsize=32:fontcolor=white:borderw=1:bordercolor=black,format=nv12,hwupload=extra_hw_frames=64" \
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
    -af aresample=async=1:first_pts=0 \
    -c:a aac \
    -b:a 64k \
    -muxdelay 0.1 \
    -f rtsp \
    -rtsp_transport tcp \
    "${DESTINATION}" &

  child_pid=$!
  watch_output "${child_pid}" "${source_pid}" &
  watchdog_pid=$!

  wait "${child_pid}"
  exit_code=$?
  child_pid=

  kill -TERM "${source_pid}" 2>/dev/null || true
  wait "${source_pid}" 2>/dev/null || true
  source_pid=

  kill "${watchdog_pid}" 2>/dev/null || true
  wait "${watchdog_pid}" 2>/dev/null || true
  watchdog_pid=

  echo "Nest clean transcoder exited with status ${exit_code}; retrying in 2 seconds" >&2
  sleep 2
done
