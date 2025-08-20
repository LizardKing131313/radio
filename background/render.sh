#!/usr/bin/env bash

ffmpeg -y \
-loop 1 -t 15 -i background.png \
-loop 1 -t 15 -i govnovoz.png \
-loop 1 -t 15 -i phone_booth.png \
-loop 1 -t 15 -i banana_stand.png \
-filter_complex "\
[0:v][1:v]overlay=enable='between(t,0,15)':x='1280-(t*120)':y=900[tmp1];\
[tmp1][2:v]overlay=enable='between(t,5,7)':x='2150-(t*200)':y=820[tmp2];\
[tmp2][3:v]overlay=enable='between(t,9,11)':x='-300 + (t*250)':y=820" \
-c:v libvpx-vp9 -b:v 12M -pix_fmt yuv420p govnovoz_vhs_v3.webm
