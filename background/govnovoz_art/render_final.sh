#!/usr/bin/env bash
set -e
ffmpeg -y \
  -loop 1 -t 15 -i background.png \
  -loop 1 -t 15 -i govnovoz.png \
  -loop 1 -t 15 -i phone_booth.png \
  -loop 1 -t 15 -i banana_stand.png \
  -filter_complex "\
[0:v][1:v]overlay=x='1280-(t*80)':y=900[v1];\
[v1][2:v]overlay=enable='between(t,5,7)':x='2600-((t-5)*300)':y=820[v2];\
[v2][3:v]overlay=enable='between(t,9,11)':x='-300+((t-9)*250)':y=820[vout]" \
  -map "[vout]" -c:v libvpx-vp9 -b:v 12M -pix_fmt yuv420p -r 60 -s 2560x1440 -t 15 govnovoz_final.webm
echo 'Done: govnovoz_final.webm'
