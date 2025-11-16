# Connection Stability Analysis

## Upstream (dwradcliffe/intellicenter)

**No active heartbeat mechanism:**
- No ping/pong implementation (despite docstring claiming it exists)
- No idle timeout monitoring
- No periodic queries
- Relies purely on:
  1. TCP keepalive (OS-level)
  2. NotifyList push messages from IntelliCenter
  3. Initial RequestParamList for attribute tracking

**Connection stays alive because:**
- IntelliCenter sends NotifyList when ANY state changes
- Most pools have frequent state changes (pumps, temp sensors, etc.)
- TCP keepalive prevents silent connection drops

## Our Fork Evolution

### v2.0.0 - Added Heartbeat with Ping/Pong
- Sent `ping\r\n` every 10 seconds
- Expected `pong` response
- Closed connection after 2 missed pongs (20 seconds)
- **Problem:** IntelliCenter doesn't actually support ping/pong protocol!

### v2.2.0 (Gold Release) - Removed Ping/Pong, Added Idle Timeout
- Removed ping/pong mechanism (correctly identified it doesn't work)
- Added 120-second idle timeout
- **Problem:** 120 seconds too aggressive for idle pools
- Caused disconnections every ~2 minutes during quiet periods

### v2.2.1 (Current) - Keepalive Queries
- Increased timeout to 300 seconds
- Added keepalive GetParamList queries every 90 seconds
- **Works but may be unnecessary**

## Root Cause of Disconnections

The disconnections weren't caused by lack of ping/pong. They were caused by:

1. **Aggressive idle timeout** (120s) added in v2.2.0
2. **Quiet periods** when pool is idle (no state changes)
3. **No data flow** triggers timeout and closes connection

## Recommended Solution

**Option 1: No Heartbeat (Upstream Approach)**
- Remove all heartbeat monitoring
- Remove idle timeout
- Rely purely on TCP keepalive + NotifyList
- Simplest, matches upstream

**Option 2: Keep Keepalive Queries (Current v2.2.1)**
- Keeps connection explicitly alive
- More robust than relying on TCP keepalive
- Minimal overhead
- Better for unreliable networks

**Option 3: Just Increase Timeout**
- Keep idle monitoring
- Set timeout to something very long (10+ minutes)
- Only catches truly dead connections
-Middle ground approach

## Decision

v2.2.1 approach (keepalive queries) is actually BETTER than upstream because:
- More robust connection handling
- Explicit keepalives vs implicit TCP
- Catches dead connections faster
- Works even if NotifyList messages are rare
- Minimal network overhead

The real bug was the 120-second idle timeout in v2.2.0, which is now fixed.
