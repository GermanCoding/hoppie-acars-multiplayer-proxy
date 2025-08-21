# Hoppie ACARS Multiplayer Proxy

A transparent proxy server for Hoppie ACARS messaging system that enables multiple clients to use a single Hoppie logon code.

The intended use-case is for shared cockpit situations: Hoppie ACARS works like a POP-mailbox, where messages are only returned to clients once. So if your aircraft polls for it callsigns, it only sees each ACARS message once. However, for shared cockpit scenarios (and possibly other multi-PC setups), you may have multiple ACARS aircraft polling messages for the same callsign.

In the Hoppie protocol this is not supported, and only one aircraft/PC will get the message. This proxy fixes this behaviour by differentiating aircraft using both callsign AND logon-code. This proxy allows you to define your own, custom log-on codes (independent of Hoppie) and each log-on code will see all messages for a given callsign, enabling shared cockpit synchronization.

The upstream (Hoppie) server used is configurable, so you can run your own network or use a different upstream (e.g. SayIntentions).

## Prerequisites

- Docker

## Environment Variables

This application requires the following environment variables:

- `HOPPIE_LOGON`: The main logon code used when talking to upstream. Usually your "actual" Hoppie logon code, or whatever else your configured upstream requires. SayIntentions requires your API key here. (required)
- `ALLOWED_LOGONS`: Comma-separated list of logon codes allowed to use this proxy. These are purely local within the proxy and do not need to exist upstream. Each ACARS client/aircraft should use an individual log-on code (especially when polling the same callsign) to differentiate them.
- `HOPPIE_UPSTREAM`: Hoppie ACARS server URL, defaults to https://www.hoppie.nl/acars/system/connect.html. SayIntentions URL is https://acars.sayintentions.ai/acars/system/connect.html

## Building and Running with Docker

### Option 1: Using Docker directly

#### Build the Docker image

```bash
docker build -t hoppie-proxy .
```

#### Run the Docker container

```bash
docker run -p 80:8000 \
  -e HOPPIE_LOGON=your_logon_code \
  -e ALLOWED_LOGONS=client1,client2,client3 \
  hoppie-proxy
```

## API Endpoint

The proxy provides the following endpoint:

- `/acars/system/connect.html`: Compatible with the Hoppie ACARS API

## Using the proxy

In order for the proxy to work, you must configure your PCs to send traffic destined for `www.hoppie.nl` to this proxy. For example, you could run this script on a server with public IP, or locally in your network. Then override your DNS resolution to resolve `www.hoppie.nl` to this proxy IP, for example by modifying your hosts file:
   * Linux: `/etc/hosts`
   * Windows: `%WinDir%\System32\drivers\etc\hosts`

To disable, just remove the entry from the hosts file. Note that while the hosts override is active, the hoppie website will not work. If you override the hosts file on the same machine as the proxy runs, the forwarding to upstream will break. To fix this, change the Hoppie URL to `http://hoppie.nl/acars/system/connect.html`.

## Development

### Running locally

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Set environment variables:
   ```
   # Linux/Mac
   export HOPPIE_LOGON=your_logon_code
   export ALLOWED_LOGONS=client1,client2,client3
   
   # Windows PowerShell
   $env:HOPPIE_LOGON = "your_logon_code"
   $env:ALLOWED_LOGONS = "client1,client2,client3"
   ```

3. Run the server:
   ```
   fastapi run
   ```
