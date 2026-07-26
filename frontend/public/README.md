# Website icon pack

This folder contains the complete favicon and PWA icon set.

## Files

- `favicon.ico` - 16, 32 and 48 pixel browser icon.
- `favicon.svg` - scalable transparent icon.
- `favicon-16x16.png`, `favicon-32x32.png`, `favicon-48x48.png` - browser PNG icons.
- `apple-touch-icon.png` - 180 pixel iOS icon.
- `android-chrome-192x192.png`, `android-chrome-512x512.png` - standard PWA icons.
- `android-chrome-192x192-maskable.png`, `android-chrome-512x512-maskable.png` - safe-zone PWA icons.
- `mstile-150x150.png` - legacy Windows tile.
- `site.webmanifest` - PWA manifest.
- `browserconfig.xml` - legacy Windows tile configuration.
- `safari-pinned-tab.svg` - monochrome Safari pinned-tab icon.
- `truck-cutout.png` - transparent high-resolution source image.

## HTML head

```html

<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon-32x32.png" sizes="32x32" type="image/png">
<link rel="icon" href="/favicon-16x16.png" sizes="16x16" type="image/png">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<link rel="mask-icon" href="/safari-pinned-tab.svg" color="#10343C">
<meta name="theme-color" content="#10343C">
<meta name="msapplication-TileColor" content="#10343C">
<meta name="msapplication-config" content="/browserconfig.xml">
```

Copy the files to the public root of the website. If the site is mounted under a subdirectory, update the leading `/`
paths in `site.webmanifest` and the HTML.

The manifest uses the generic name `Radio`; replace `name` and `short_name` with the final site name before deployment.
