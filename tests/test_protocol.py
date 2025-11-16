"""Tests for pyintellicenter protocol module."""

import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.intellicenter.pyintellicenter.protocol import (
    CONNECTION_IDLE_TIMEOUT,
    FLOW_CONTROL_TIMEOUT,
    HEARTBEAT_INTERVAL,
    KEEPALIVE_INTERVAL,
    ICProtocol,
)


class MockController:
    """Mock controller for testing protocol."""

    def __init__(self):
        """Initialize mock controller."""
        self.connection_made_called = False
        self.connection_lost_called = False
        self.received_messages = []

    def connection_made(self, protocol, transport):
        """Handle connection made callback."""
        self.connection_made_called = True

    def connection_lost(self, exc):
        """Handle connection lost callback."""
        self.connection_lost_called = True

    def receivedMessage(self, msg_id, command, response, msg):
        """Handle received message callback."""
        self.received_messages.append((msg_id, command, response, msg))


@pytest.fixture
def mock_controller():
    """Create a mock controller."""
    return MockController()


@pytest.fixture
def protocol(mock_controller):
    """Create a protocol instance."""
    return ICProtocol(mock_controller)


@pytest.fixture
def mock_transport():
    """Create a mock transport."""
    transport = Mock()
    transport.write = Mock()
    transport.close = Mock()
    transport.is_closing = Mock(return_value=False)
    return transport


class TestICProtocolInit:
    """Test ICProtocol initialization."""

    def test_init(self, mock_controller):
        """Test protocol initialization."""
        protocol = ICProtocol(mock_controller)

        assert protocol._controller == mock_controller
        assert protocol._transport is None
        assert protocol._msgID == 1
        assert protocol._lineBuffer == ""
        assert protocol._out_pending == 0
        assert not protocol._out_queue.empty() is False
        assert protocol._last_flow_control_activity is None
        assert protocol._last_data_received is None
        assert protocol._last_keepalive_sent is None
        assert protocol._heartbeat_task is None


class TestICProtocolConnection:
    """Test ICProtocol connection handling."""

    def test_connection_made(self, protocol, mock_transport, mock_controller):
        """Test connection_made callback."""
        protocol.connection_made(mock_transport)

        assert protocol._transport == mock_transport
        assert protocol._msgID == 1
        assert protocol._last_flow_control_activity is not None
        assert protocol._last_data_received is not None
        assert protocol._last_keepalive_sent is not None
        assert protocol._heartbeat_task is not None
        assert mock_controller.connection_made_called

    async def test_connection_lost(self, protocol, mock_transport, mock_controller):
        """Test connection_lost callback."""
        # First establish connection
        protocol.connection_made(mock_transport)

        # Then lose it
        protocol.connection_lost(None)

        # Wait for heartbeat task to be cancelled
        await asyncio.sleep(0.1)

        assert mock_controller.connection_lost_called
        assert protocol._heartbeat_task is None or protocol._heartbeat_task.done()


class TestICProtocolDataReceived:
    """Test ICProtocol data receiving."""

    def test_data_received_partial_message(self, protocol, mock_transport):
        """Test receiving partial message."""
        protocol.connection_made(mock_transport)

        # Send partial message (no \r\n terminator)
        protocol.data_received(b'{"messageID": "1", "command": "Test"')

        # Message should be buffered
        assert protocol._lineBuffer == '{"messageID": "1", "command": "Test"'
        assert len(protocol._controller.received_messages) == 0

    def test_data_received_complete_message(self, protocol, mock_transport):
        """Test receiving complete message."""
        protocol.connection_made(mock_transport)

        # Send complete message
        message = {"messageID": "1", "command": "Test", "response": "200"}
        protocol.data_received((json.dumps(message) + "\r\n").encode())

        # Message should be processed
        assert protocol._lineBuffer == ""
        assert len(protocol._controller.received_messages) == 1
        assert protocol._controller.received_messages[0][0] == "1"
        assert protocol._controller.received_messages[0][1] == "Test"
        assert protocol._controller.received_messages[0][2] == "200"

    def test_data_received_multiple_messages(self, protocol, mock_transport):
        """Test receiving multiple messages in one chunk."""
        protocol.connection_made(mock_transport)

        # Send multiple messages
        msg1 = {"messageID": "1", "command": "Test1", "response": "200"}
        msg2 = {"messageID": "2", "command": "Test2", "response": "200"}
        data = json.dumps(msg1) + "\r\n" + json.dumps(msg2) + "\r\n"
        protocol.data_received(data.encode())

        # Both messages should be processed
        assert len(protocol._controller.received_messages) == 2

    def test_data_received_buffered_completion(self, protocol, mock_transport):
        """Test completing buffered message."""
        protocol.connection_made(mock_transport)

        # Send partial message
        protocol.data_received(b'{"messageID": "1",')
        assert len(protocol._controller.received_messages) == 0

        # Complete the message
        protocol.data_received(b' "command": "Test", "response": "200"}\r\n')
        assert len(protocol._controller.received_messages) == 1


class TestICProtocolSendCmd:
    """Test ICProtocol command sending."""

    def test_sendCmd_basic(self, protocol, mock_transport):
        """Test sending basic command."""
        protocol.connection_made(mock_transport)

        msg_id = protocol.sendCmd("GetParamList")

        assert msg_id == "1"
        assert protocol._msgID == 2
        mock_transport.write.assert_called_once()

        # Check the message format
        call_args = mock_transport.write.call_args[0][0]
        message = json.loads(call_args.decode())
        assert message["messageID"] == "1"
        assert message["command"] == "GetParamList"

    def test_sendCmd_with_extra(self, protocol, mock_transport):
        """Test sending command with extra parameters."""
        protocol.connection_made(mock_transport)

        extra = {"condition": "OBJTYP=SYSTEM"}
        msg_id = protocol.sendCmd("GetParamList", extra)

        assert msg_id == "1"

        # Check the message includes extra params
        call_args = mock_transport.write.call_args[0][0]
        message = json.loads(call_args.decode())
        assert message["command"] == "GetParamList"
        assert message["condition"] == "OBJTYP=SYSTEM"

    def test_sendCmd_increments_id(self, protocol, mock_transport):
        """Test message ID increments."""
        protocol.connection_made(mock_transport)

        id1 = protocol.sendCmd("Test1")
        id2 = protocol.sendCmd("Test2")
        id3 = protocol.sendCmd("Test3")

        assert id1 == "1"
        assert id2 == "2"
        assert id3 == "3"


class TestICProtocolFlowControl:
    """Test ICProtocol flow control."""

    def test_flow_control_single_request(self, protocol, mock_transport):
        """Test flow control with single request."""
        protocol.connection_made(mock_transport)

        protocol.sendCmd("Test")

        assert protocol._out_pending == 1
        assert protocol._out_queue.empty()
        mock_transport.write.assert_called_once()

    def test_flow_control_multiple_requests(self, protocol, mock_transport):
        """Test flow control queues concurrent requests."""
        protocol.connection_made(mock_transport)

        # Send first request (goes to wire)
        protocol.sendCmd("Test1")
        assert protocol._out_pending == 1
        assert protocol._out_queue.empty()

        # Send second request (queued)
        protocol.sendCmd("Test2")
        assert protocol._out_pending == 2
        assert not protocol._out_queue.empty()

        # Only first request should be sent
        assert mock_transport.write.call_count == 1

    def test_flow_control_response_sends_queued(self, protocol, mock_transport):
        """Test flow control sends queued request on response."""
        protocol.connection_made(mock_transport)

        # Queue multiple requests
        protocol.sendCmd("Test1")
        protocol.sendCmd("Test2")

        # First request sent
        assert mock_transport.write.call_count == 1

        # Simulate response
        protocol.responseReceived()

        # Second request should be sent
        assert mock_transport.write.call_count == 2
        assert protocol._out_pending == 1

    def test_flow_control_pending_decrements(self, protocol, mock_transport):
        """Test pending counter decrements on response."""
        protocol.connection_made(mock_transport)

        protocol.sendCmd("Test")
        assert protocol._out_pending == 1

        protocol.responseReceived()
        assert protocol._out_pending == 0


class TestICProtocolProcessMessage:
    """Test ICProtocol message processing."""

    def test_processMessage_valid_response(self, protocol, mock_transport):
        """Test processing valid response message."""
        protocol.connection_made(mock_transport)

        message = json.dumps(
            {"messageID": "1", "command": "Test", "response": "200", "data": "value"}
        )
        protocol.processMessage(message)

        assert len(protocol._controller.received_messages) == 1
        msg_id, command, response, msg = protocol._controller.received_messages[0]
        assert msg_id == "1"
        assert command == "Test"
        assert response == "200"
        assert msg["data"] == "value"

    def test_processMessage_notification(self, protocol, mock_transport):
        """Test processing notification (no response field)."""
        protocol.connection_made(mock_transport)

        message = json.dumps({"messageID": "1", "command": "NotifyList"})
        protocol.processMessage(message)

        assert len(protocol._controller.received_messages) == 1
        msg_id, command, response, msg = protocol._controller.received_messages[0]
        assert msg_id == "1"
        assert command == "NotifyList"
        assert response is None

    def test_processMessage_invalid_json(self, protocol, mock_transport):
        """Test processing invalid JSON."""
        protocol.connection_made(mock_transport)

        # Should not crash
        protocol.processMessage("not valid json")

        # Should not trigger controller callback
        assert len(protocol._controller.received_messages) == 0

    def test_processMessage_missing_fields(self, protocol, mock_transport):
        """Test processing message with missing fields."""
        protocol.connection_made(mock_transport)

        # Missing command field
        message = json.dumps({"messageID": "1", "response": "200"})
        protocol.processMessage(message)

        # Should not trigger controller callback
        assert len(protocol._controller.received_messages) == 0

    def test_processMessage_unexpected_error_closes_connection(
        self, protocol, mock_transport
    ):
        """Test unexpected error closes connection."""
        protocol.connection_made(mock_transport)

        # Simulate controller raising unexpected exception
        def raise_error(*args):
            raise RuntimeError("Unexpected error")

        protocol._controller.receivedMessage = raise_error

        message = json.dumps({"messageID": "1", "command": "Test", "response": "200"})
        protocol.processMessage(message)

        # Connection should be closed
        mock_transport.close.assert_called_once()


class TestICProtocolHeartbeat:
    """Test ICProtocol heartbeat functionality."""

    async def test_heartbeat_task_created(self, protocol, mock_transport):
        """Test heartbeat task is created on connection."""
        protocol.connection_made(mock_transport)

        assert protocol._heartbeat_task is not None
        assert not protocol._heartbeat_task.done()

        # Cleanup
        protocol.connection_lost(None)
        await asyncio.sleep(0.1)

    async def test_heartbeat_sends_keepalive(self, protocol, mock_transport):
        """Test heartbeat sends keepalive queries."""
        protocol.connection_made(mock_transport)

        # Set last keepalive far in the past
        protocol._last_keepalive_sent = asyncio.get_event_loop().time() - (
            KEEPALIVE_INTERVAL + 10
        )

        # Wait for heartbeat to run
        await asyncio.sleep(HEARTBEAT_INTERVAL + 1)

        # Should have sent keepalive
        # (at least 2 calls: initial connection message + keepalive)
        assert mock_transport.write.call_count >= 2

        # Cleanup
        protocol.connection_lost(None)
        await asyncio.sleep(0.1)

    async def test_heartbeat_detects_idle_timeout(self, protocol, mock_transport):
        """Test heartbeat detects idle connection."""
        protocol.connection_made(mock_transport)

        # Set last data far in the past
        protocol._last_data_received = asyncio.get_event_loop().time() - (
            CONNECTION_IDLE_TIMEOUT + 10
        )

        # Wait for heartbeat to detect timeout
        await asyncio.sleep(HEARTBEAT_INTERVAL + 1)

        # Connection should be closed
        mock_transport.close.assert_called()

        # Cleanup
        await asyncio.sleep(0.1)

    async def test_heartbeat_detects_flow_control_deadlock(
        self, protocol, mock_transport
    ):
        """Test heartbeat detects and resets flow control deadlock."""
        protocol.connection_made(mock_transport)

        # Simulate deadlock: pending requests with no activity
        protocol._out_pending = 5
        protocol._out_queue.put("queued1")
        protocol._out_queue.put("queued2")
        protocol._last_flow_control_activity = asyncio.get_event_loop().time() - (
            FLOW_CONTROL_TIMEOUT + 10
        )

        # Wait for heartbeat to detect deadlock
        await asyncio.sleep(HEARTBEAT_INTERVAL + 1)

        # Flow control should be reset
        assert protocol._out_pending == 0
        assert protocol._out_queue.empty()

        # Cleanup
        protocol.connection_lost(None)
        await asyncio.sleep(0.1)

    async def test_heartbeat_cancelled_on_disconnect(self, protocol, mock_transport):
        """Test heartbeat task is cancelled on disconnect."""
        protocol.connection_made(mock_transport)

        heartbeat_task = protocol._heartbeat_task
        assert not heartbeat_task.done()

        protocol.connection_lost(None)
        await asyncio.sleep(0.1)

        # Task should be cancelled
        assert heartbeat_task.cancelled() or heartbeat_task.done()
