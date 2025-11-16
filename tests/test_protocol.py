"""Tests for pyintellicenter protocol module."""

import asyncio
import json
from unittest.mock import Mock

import pytest

from custom_components.intellicenter.pyintellicenter.protocol import (
    CONNECTION_IDLE_TIMEOUT,
    FLOW_CONTROL_TIMEOUT,
    HEARTBEAT_INTERVAL,
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
        assert protocol._out_queue.empty()
        assert protocol._last_flow_control_activity is None
        assert protocol._last_data_received is None
        assert protocol._last_keepalive_sent is None
        assert protocol._heartbeat_task is None


class TestICProtocolConnection:
    """Test ICProtocol connection handling."""

    async def test_connection_made(self, mock_controller, mock_transport):
        """Test connection_made callback."""
        protocol = ICProtocol(mock_controller)
        protocol.connection_made(mock_transport)

        assert protocol._transport == mock_transport
        assert protocol._msgID == 1
        assert protocol._last_flow_control_activity is not None
        assert protocol._last_data_received is not None
        assert protocol._last_keepalive_sent is not None
        assert protocol._heartbeat_task is not None
        assert mock_controller.connection_made_called

        # Cleanup
        protocol.connection_lost(None)
        await asyncio.sleep(0.1)

    async def test_connection_lost(self, mock_controller, mock_transport):
        """Test connection_lost callback."""
        protocol = ICProtocol(mock_controller)

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

    async def test_data_received_complete_message(self, mock_controller, mock_transport):
        """Test receiving complete message."""
        protocol = ICProtocol(mock_controller)
        protocol.connection_made(mock_transport)

        # Send complete message
        message = {"messageID": "1", "command": "Test", "response": "200"}
        protocol.data_received((json.dumps(message) + "\r\n").encode())

        # Message should be processed
        assert protocol._lineBuffer == ""
        assert len(mock_controller.received_messages) == 1
        assert mock_controller.received_messages[0][0] == "1"
        assert mock_controller.received_messages[0][1] == "Test"
        assert mock_controller.received_messages[0][2] == "200"

        # Cleanup
        protocol.connection_lost(None)
        await asyncio.sleep(0.1)

    async def test_data_received_multiple_messages(self, mock_controller, mock_transport):
        """Test receiving multiple messages in one chunk."""
        protocol = ICProtocol(mock_controller)
        protocol.connection_made(mock_transport)

        # Send multiple messages
        msg1 = {"messageID": "1", "command": "Test1", "response": "200"}
        msg2 = {"messageID": "2", "command": "Test2", "response": "200"}
        data = json.dumps(msg1) + "\r\n" + json.dumps(msg2) + "\r\n"
        protocol.data_received(data.encode())

        # Both messages should be processed
        assert len(mock_controller.received_messages) == 2

        # Cleanup
        protocol.connection_lost(None)
        await asyncio.sleep(0.1)


class TestICProtocolProcessMessage:
    """Test ICProtocol message processing."""

    async def test_processMessage_valid_response(self, mock_controller, mock_transport):
        """Test processing valid response message."""
        protocol = ICProtocol(mock_controller)
        protocol.connection_made(mock_transport)

        message = json.dumps(
            {"messageID": "1", "command": "Test", "response": "200", "data": "value"}
        )
        protocol.processMessage(message)

        assert len(mock_controller.received_messages) == 1
        msg_id, command, response, msg = mock_controller.received_messages[0]
        assert msg_id == "1"
        assert command == "Test"
        assert response == "200"
        assert msg["data"] == "value"

        # Cleanup
        protocol.connection_lost(None)
        await asyncio.sleep(0.1)

    async def test_processMessage_notification(self, mock_controller, mock_transport):
        """Test processing notification (no response field)."""
        protocol = ICProtocol(mock_controller)
        protocol.connection_made(mock_transport)

        message = json.dumps({"messageID": "1", "command": "NotifyList"})
        protocol.processMessage(message)

        assert len(mock_controller.received_messages) == 1
        msg_id, command, response, msg = mock_controller.received_messages[0]
        assert msg_id == "1"
        assert command == "NotifyList"
        assert response is None

        # Cleanup
        protocol.connection_lost(None)
        await asyncio.sleep(0.1)


class TestICProtocolHeartbeat:
    """Test ICProtocol heartbeat functionality."""

    async def test_heartbeat_task_created(self, mock_controller, mock_transport):
        """Test heartbeat task is created on connection."""
        protocol = ICProtocol(mock_controller)
        protocol.connection_made(mock_transport)

        assert protocol._heartbeat_task is not None
        assert not protocol._heartbeat_task.done()

        # Cleanup
        protocol.connection_lost(None)
        await asyncio.sleep(0.1)

    async def test_heartbeat_detects_idle_timeout(self, mock_controller, mock_transport):
        """Test heartbeat detects idle connection."""
        protocol = ICProtocol(mock_controller)
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
        self, mock_controller, mock_transport
    ):
        """Test heartbeat detects and resets flow control deadlock."""
        protocol = ICProtocol(mock_controller)
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

    async def test_heartbeat_cancelled_on_disconnect(self, mock_controller, mock_transport):
        """Test heartbeat task is cancelled on disconnect."""
        protocol = ICProtocol(mock_controller)
        protocol.connection_made(mock_transport)

        heartbeat_task = protocol._heartbeat_task
        assert not heartbeat_task.done()

        protocol.connection_lost(None)
        await asyncio.sleep(0.1)

        # Task should be cancelled
        assert heartbeat_task.cancelled() or heartbeat_task.done()
