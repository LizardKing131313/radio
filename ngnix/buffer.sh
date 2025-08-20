sudo -u www-data ffmpeg -hide_banner -loglevel warning \
  -fflags +nobuffer -flags low_delay -probesize 32k -analyzeduration 0 -icy 0 \
  -i http://127.0.0.1:8443/stream \
  -c:a copy -bsf:a aac_adtstoasc \
  -f hls -hls_time 5 -hls_list_size 8 \
  -hls_flags delete_segments+independent_segments \
  -hls_segment_type fmp4 \
  -master_pl_name master.m3u8 \
  -hls_segment_filename /var/www/radio/seg_%05d.m4s \
  /var/www/radio/playlist.m3u8
