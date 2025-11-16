#!/usr/bin/env python3
"""Script to connect to IntelliCenter and explore valve objects."""

import asyncio
import json
import sys


# Simple protocol to communicate with IntelliCenter
class SimpleICProtocol(asyncio.Protocol):
    """Simple protocol to query IntelliCenter."""

    def __init__(self, on_data):
        self._on_data = on_data
        self._buffer = ""
        self._transport = None
        self._msg_id = 1

    def connection_made(self, transport):
        """Connection established."""
        self._transport = transport
        print("Connected to IntelliCenter")

        # Request all objects with all attributes
        self.send_command(
            "GetParamList",
            {
                "condition": "",
                "objectList": [
                    {
                        "objnam": "INCR",
                        "keys": [
                            "OBJTYP",
                            "SUBTYP",
                            "SNAME",
                            "ASSIGN",
                            "DLY",
                            "PARENT",
                            "CIRCUIT",
                            "STATIC",
                            "HNAME",
                        ],
                    }
                ],
            },
        )

    def data_received(self, data):
        """Data received from IntelliCenter."""
        self._buffer += data.decode()

        # Process complete lines
        while "\r\n" in self._buffer:
            line, self._buffer = self._buffer.split("\r\n", 1)
            if line:
                try:
                    msg = json.loads(line)
                    self._on_data(msg)
                except json.JSONDecodeError as e:
                    print(f"JSON decode error: {e}")
                    print(f"Line: {line}")

    def send_command(self, command, extra=None):
        """Send a command to IntelliCenter."""
        msg = {"messageID": str(self._msg_id), "command": command}
        if extra:
            msg.update(extra)

        self._msg_id += 1
        packet = json.dumps(msg) + "\r\n"
        print(f"Sending: {msg}")
        self._transport.write(packet.encode())

    def connection_lost(self, exc):
        """Connection lost."""
        print(f"Connection lost: {exc}")


class IntelliCenterExplorer:
    """Explore IntelliCenter objects."""

    def __init__(self, host, port=6681):
        self.host = host
        self.port = port
        self.objects = []
        self.valve_objects = []

    def on_data(self, msg):
        """Handle received messages."""
        print(f"\n{'='*80}")
        print(f"Received message: {msg.get('command', msg.get('response'))}")
        print(f"{'='*80}")

        # Check for object list
        if "objectList" in msg:
            for obj in msg["objectList"]:
                objnam = obj.get("objnam", "UNKNOWN")
                params = obj.get("params", {})
                objtyp = params.get("OBJTYP", "UNKNOWN")

                self.objects.append(obj)

                # Track valve objects
                if objtyp == "VALVE":
                    print(f"\n🎯 FOUND VALVE OBJECT: {objnam}")
                    print(json.dumps(obj, indent=2))
                    self.valve_objects.append(obj)

        # Pretty print for debugging
        print(json.dumps(msg, indent=2))

    async def explore(self):
        """Connect and explore."""
        loop = asyncio.get_event_loop()

        try:
            print(f"Connecting to {self.host}:{self.port}...")
            transport, protocol = await loop.create_connection(
                lambda: SimpleICProtocol(self.on_data), self.host, self.port
            )

            # Wait for data
            print("\nWaiting for responses (30 seconds)...")
            await asyncio.sleep(30)

            # Close connection
            transport.close()

            # Print summary
            print(f"\n{'='*80}")
            print("SUMMARY")
            print(f"{'='*80}")
            print(f"Total objects received: {len(self.objects)}")
            print(f"Valve objects found: {len(self.valve_objects)}")

            if self.valve_objects:
                print("\n📋 VALVE OBJECTS DETAIL:")
                for valve in self.valve_objects:
                    print(f"\n{'-'*80}")
                    print(json.dumps(valve, indent=2))

                # Save to file
                with open(
                    "/Users/bryanli/Projects/joyfulhouse/homeassistant-dev/intellicenter/valve_objects.json",
                    "w",
                ) as f:
                    json.dump(
                        {
                            "valve_count": len(self.valve_objects),
                            "valves": self.valve_objects,
                            "all_objects": self.objects,
                        },
                        f,
                        indent=2,
                    )
                print("\n✅ Saved valve data to valve_objects.json")
            else:
                print("\n⚠️  No VALVE objects found in system")
                print("\nAll object types found:")
                types = {}
                for obj in self.objects:
                    objtyp = obj.get("params", {}).get("OBJTYP", "UNKNOWN")
                    types[objtyp] = types.get(objtyp, 0) + 1

                for objtyp, count in sorted(types.items()):
                    print(f"  {objtyp}: {count}")

        except Exception as e:
            print(f"Error: {e}")
            import traceback

            traceback.print_exc()


async def main():
    """Main entry point."""
    host = "10.100.11.60"

    if len(sys.argv) > 1:
        host = sys.argv[1]

    explorer = IntelliCenterExplorer(host)
    await explorer.explore()


if __name__ == "__main__":
    asyncio.run(main())
