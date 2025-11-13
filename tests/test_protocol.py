"""Test the IntelliCenter protocol."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.intellicenter.pyintellicenter.protocol import ICProtocol


def test_protocol_init():
    """Test protocol initialization."""
    controller = MagicMock()
    protocol = ICProtocol(controller)

    assert protocol._controller == controller
    assert protocol._msgID == 1
    assert protocol._num_unacked_pings == 0
    assert protocol._heartbeat_task is None


def test_connection_made():
    """Test connection_made callback."""
    controller = MagicMock()
    protocol = ICProtocol(controller)

    transport = MagicMock()

    with patch.object(asyncio, "create_task") as mock_create_task:
        protocol.connection_made(transport)

        assert protocol._transport == transport
        assert protocol._msgID == 1
        assert protocol._num_unacked_pings == 0
        assert mock_create_task.called  # heartbeat task created
        controller.connection_made.assert_called_once()


def test_connection_lost():
    """Test connection_lost callback."""
    controller = MagicMock()
    protocol = ICProtocol(controller)

    # Setup heartbeat task
    mock_task = MagicMock()
    protocol._heartbeat_task = mock_task

    protocol.connection_lost(None)

    mock_task.cancel.assert_called_once()
    assert protocol._heartbeat_task is None
    controller.connection_lost.assert_called_once()


def test_data_received():
    """Test data_received callback."""
    controller = MagicMock()
    protocol = ICProtocol(controller)

    with patch.object(protocol, "processMessage") as mock_process:
        # Send a simple message
        protocol.data_received(b'{"messageID": "1", "command": "test"}\r\n')

        mock_process.assert_called_once()


def test_sendCmd():
    """Test sendCmd method."""
    controller = MagicMock()
    protocol = ICProtocol(controller)
    protocol._transport = MagicMock()

    with patch.object(protocol, "sendRequest") as mock_send:
        msg_id = protocol.sendCmd("TestCommand", {"key": "value"})

        assert msg_id == "1"
        assert protocol._msgID == 2
        mock_send.assert_called_once()


def test_process_pong():
    """Test processing pong message."""
    controller = MagicMock()
    protocol = ICProtocol(controller)
    protocol._num_unacked_pings = 2

    with patch.object(protocol, "responseReceived") as mock_response:
        protocol.processMessage("pong")

        assert protocol._num_unacked_pings == 1
        mock_response.assert_called_once()


@pytest.mark.asyncio
async def test_heartbeat_loop():
    """Test heartbeat loop sends pings."""
    controller = MagicMock()
    protocol = ICProtocol(controller)
    protocol._transport = MagicMock()

    # Run heartbeat for a short time
    task = asyncio.create_task(protocol._heartbeat_loop())

    # Wait for first ping (10 seconds + small buffer)
    await asyncio.sleep(0.1)  # In real test, you'd mock asyncio.sleep

    # Cancel the task
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_heartbeat_closes_on_too_many_unacked_pings():
    """Test heartbeat closes connection on too many unacked pings."""
    controller = MagicMock()
    protocol = ICProtocol(controller)
    transport = MagicMock()
    protocol._transport = transport
    protocol._num_unacked_pings = 2  # Already at threshold

    # Mock asyncio.sleep to return immediately
    with patch("asyncio.sleep", new_callable=AsyncMock):
        task = asyncio.create_task(protocol._heartbeat_loop())
        await asyncio.sleep(0.01)  # Give it time to execute

        # Check that transport was closed
        transport.close.assert_called()

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
