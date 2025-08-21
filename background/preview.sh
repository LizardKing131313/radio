#!/usr/bin/env bash

ffmpeg -y \
  -loop 1 -t 6 -i background.png \
  -loop 1 -t 6 -i govnovoz.png \
  -loop 1 -t 6 -i phone_booth.png \
  -loop 1 -t 6 -i banana_stand.png \
  -filter_complex "\
[0:v][1:v]overlay=x='1280-(t*80)':y=900[tmp1]; \
[tmp1][2:v]overlay=enable='between(t,1,3)':x='2150-(t*200)':y=820[tmp2]; \
[tmp2][3:v]overlay=enable='between(t,4,6)':x='-300+(t*200)':y=820" \
  -c:v libvpx-vp9 -b:v 4M -pix_fmt yuv420p preview.webm
