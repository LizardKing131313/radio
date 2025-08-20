#!/usr/bin/env bash

ffmpeg -y -f lavfi -i color=c=black:s=2560x1440:r=60:d=15 \
-vf "
geq='lum(X,Y)+20*sin(0.5*Y/1440)':cb='128':cr='128',
colorbalance=rs=.05:bs=.08,
drawbox=x=0:y=1200:w=2560:h=240:color=#222222@1:t=fill,
perspective=x0=0:y0=1200:x1=2560:y1=1200:x2=1900:y2=850:x3=660:y3=850,

drawbox=x=1280-(t*120):y=900:w=240:h=120:color=#FF7700@1,
drawbox=x=1300-(t*120):y=870:w=90:h=90:color=#444444@1,

drawbox=x=1310-(t*120):y=860:w=20:h=20:color=#FFA500@0.8,
drawbox=x=1370-(t*120):y=860:w=20:h=20:color=#FFA500@0.8,

drawbox=enable='between(t,5,7)':x=2150-(t*200):y=820:w=60:h=150:color=#88aaff@1,

drawbox=enable='between(t,9,11)':x=150-(t*250):y=820:w=120:h=150:color=#FCE205@1,

drawbox=x=1180:y=600:w=350:h=200:color=#0000FF@0.7,

noise=alls=10:allf=t,
format=yuv420p
" \
-c:v libvpx-vp9 -b:v 12M -pix_fmt yuv420p govnovoz_vhs_v2.webm
