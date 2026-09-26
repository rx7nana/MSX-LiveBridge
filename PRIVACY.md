# MSX LiveBridge Privacy Policy

Last updated: September 27, 2026

MSX LiveBridge is a Chromium extension and Windows application for connecting msxplay with MSX hardware through VSIF.

## Data handled by the Chromium extension

The MSX LiveBridge Chromium extension handles only the data necessary to provide MSX hardware playback functionality.

This may include:

- MGS music data obtained from msxplay
- Playback commands such as PLAY, PAUSE, RESUME, STOP, and SEEK
- Playback position, timing, and end-of-playback information
- Temporary playback session identifiers
- Authentication information used to communicate with the MSX LiveBridge Windows application
- The source URL, used only to verify that messages originate from the permitted msxplay website

## How the data is used

The data is used solely to connect msxplay with the MSX LiveBridge Windows application and reproduce playback on the user's own MSX hardware.

The extension communicates only with:

- `https://msxplay.com/*`
- the MSX LiveBridge Windows application running on the same computer through `http://127.0.0.1:27183/*`

## Local storage

The extension temporarily stores playback tab, playback session, and Windows application instance information using `chrome.storage.session` so that playback control can continue correctly if the extension's background process restarts.

Authentication tokens are not stored in `chrome.storage.session`.

The Windows application may store received MGS data, converted playback data, and diagnostic logs locally on the user's computer for playback processing and troubleshooting. Playback processing data is normally retained for only the most recent runs.

## Data sharing

MSX LiveBridge does not send user data to the developer, external servers, advertising services, or other third parties.

MSX LiveBridge does not sell user data.

User data is not used for advertising, creditworthiness, lending, or any purpose unrelated to MSX hardware playback.

## Browsing information

The extension checks the source URL of messages only to verify that they originate from the permitted msxplay website.

It does not collect, store, or transmit the user's general browsing history.

## Remote code

The extension does not download or execute remote JavaScript, WebAssembly, or other executable code.

All executable JavaScript used by the extension is included in the extension package.

## Contact

For questions about this privacy policy, please use the GitHub repository for MSX LiveBridge.
