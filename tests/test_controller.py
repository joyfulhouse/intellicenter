"""Tests for pyintellicenter controller module."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.intellicenter.pyintellicenter.controller import (
    BaseController,
    CommandError,
    ConnectionHandler,
    ModelController,
    SystemInfo,
    prune,
)
from custom_components.intellicenter.pyintellicenter.model import PoolModel


class TestPrune:
    """Test prune function."""

    def test_prune_dict_removes_undefined(self):
        """Test pruning removes key==value entries."""
        obj = {"key1": "value1", "key2": "key2", "key3": "value3"}
        result = prune(obj)

        assert result == {"key1": "value1", "key3": "value3"}
        assert "key2" not in result

    def test_prune_nested_dict(self):
        """Test pruning nested dictionaries."""
        obj = {"outer": {"inner1": "value1", "inner2": "inner2"}, "keep": "value"}
        result = prune(obj)

        assert result == {"outer": {"inner1": "value1"}, "keep": "value"}

    def test_prune_list(self):
        """Test pruning lists."""
        obj = [
            {"key1": "value1", "key2": "key2"},
            {"key3": "value3"},
        ]
        result = prune(obj)

        assert result == [{"key1": "value1"}, {"key3": "value3"}]

    def test_prune_primitives(self):
        """Test pruning primitive values."""
        assert prune("string") == "string"
        assert prune(42) == 42
        assert prune(None) is None


class TestCommandError:
    """Test CommandError exception."""

    def test_init(self):
        """Test CommandError initialization."""
        error = CommandError("400")

        assert error.errorCode == "400"
        assert "400" in str(error)

    def test_inheritance(self):
        """Test CommandError is an Exception."""
        error = CommandError("500")
        assert isinstance(error, Exception)


class TestSystemInfo:
    """Test SystemInfo class."""

    def test_init(self):
        """Test SystemInfo initialization."""
        params = {
            "PROPNAME": "My Pool",
            "VER": "1.0.5",
            "MODE": "METRIC",
            "SNAME": "IntelliCenter",
        }
        info = SystemInfo("INCR", params)

        assert info.propName == "My Pool"
        assert info.swVersion == "1.0.5"
        assert info.usesMetric is True
        assert info.uniqueID is not None
        assert len(info.uniqueID) == 16  # blake2b with digest_size=8 produces 16 hex chars

    def test_uses_english(self):
        """Test system using English units."""
        params = {
            "PROPNAME": "My Pool",
            "VER": "1.0.5",
            "MODE": "ENGLISH",
            "SNAME": "IntelliCenter",
        }
        info = SystemInfo("INCR", params)

        assert info.usesMetric is False

    def test_update(self):
        """Test updating system info."""
        params = {
            "PROPNAME": "Pool 1",
            "VER": "1.0.0",
            "MODE": "METRIC",
            "SNAME": "IntelliCenter",
        }
        info = SystemInfo("INCR", params)

        info.update({"PROPNAME": "Pool 2", "VER": "1.0.1"})

        assert info.propName == "Pool 2"
        assert info.swVersion == "1.0.1"
        assert info.usesMetric is True

    def test_unique_id_stable(self):
        """Test unique ID is stable for same system name."""
        params1 = {
            "PROPNAME": "Pool 1",
            "VER": "1.0.0",
            "MODE": "METRIC",
            "SNAME": "System1",
        }
        params2 = {
            "PROPNAME": "Pool 2",
            "VER": "2.0.0",
            "MODE": "ENGLISH",
            "SNAME": "System1",
        }

        info1 = SystemInfo("INCR", params1)
        info2 = SystemInfo("INCR", params2)

        # Same SNAME should produce same unique ID
        assert info1.uniqueID == info2.uniqueID


class TestBaseController:
    """Test BaseController class."""

    @pytest.fixture
    def mock_loop(self):
        """Create mock event loop."""
        loop = asyncio.get_event_loop()
        return loop

    @pytest.fixture
    def controller(self, mock_loop):
        """Create a BaseController instance."""
        return BaseController("192.168.1.100", 6681, mock_loop)

    def test_init(self, controller):
        """Test BaseController initialization."""
        assert controller.host == "192.168.1.100"
        assert controller._port == 6681
        assert controller._transport is None
        assert controller._protocol is None
        assert controller._systemInfo is None
        assert controller._requests == {}

    def test_connection_made_callback(self, controller):
        """Test connection_made callback."""
        mock_protocol = Mock()
        mock_transport = Mock()

        controller.connection_made(mock_protocol, mock_transport)

        # Should not raise error
        assert True

    def test_connection_lost_callback(self, controller):
        """Test connection_lost callback."""
        callback_called = False

        def disconnect_callback(ctrl, exc):
            nonlocal callback_called
            callback_called = True

        controller._diconnectedCallback = disconnect_callback

        controller.connection_lost(None)

        assert callback_called

    async def test_start(self, controller, mock_loop):
        """Test starting controller."""
        with patch.object(
            mock_loop, "create_connection"
        ) as mock_create_connection, patch.object(
            controller, "sendCmd"
        ) as mock_send_cmd:
            # Mock the connection creation
            mock_protocol = Mock()
            mock_transport = Mock()
            mock_create_connection.return_value = (mock_transport, mock_protocol)

            # Mock the GetParamList response
            mock_send_cmd.return_value = asyncio.Future()
            mock_send_cmd.return_value.set_result(
                {
                    "objectList": [
                        {
                            "objnam": "INCR",
                            "params": {
                                "PROPNAME": "Test Pool",
                                "VER": "1.0.0",
                                "MODE": "METRIC",
                                "SNAME": "TestSystem",
                            },
                        }
                    ]
                }
            )

            await controller.start()

            assert controller._systemInfo is not None
            assert controller._systemInfo.propName == "Test Pool"
            assert controller._systemInfo.swVersion == "1.0.0"

    def test_stop(self, controller):
        """Test stopping controller."""
        # Create mock transport and pending requests
        controller._transport = Mock()
        future1 = asyncio.Future()
        future2 = asyncio.Future()
        controller._requests = {"1": future1, "2": future2}

        controller.stop()

        assert controller._transport is None
        assert controller._protocol is None
        assert future1.cancelled()
        assert future2.cancelled()

    def test_sendCmd_creates_future(self, controller):
        """Test sendCmd creates future when waiting for response."""
        controller._protocol = Mock()
        controller._protocol.sendCmd = Mock(return_value="1")

        future = controller.sendCmd("GetParamList")

        assert future is not None
        assert isinstance(future, asyncio.Future)
        assert "1" in controller._requests

    def test_sendCmd_no_future(self, controller):
        """Test sendCmd without waiting for response."""
        controller._protocol = Mock()
        controller._protocol.sendCmd = Mock(return_value="1")

        future = controller.sendCmd("GetParamList", waitForResponse=False)

        assert future is None
        assert controller._requests["1"] is None

    def test_sendCmd_disconnected(self, controller):
        """Test sendCmd when disconnected."""
        future = controller.sendCmd("GetParamList")

        assert isinstance(future, asyncio.Future)
        assert future.done()
        with pytest.raises(Exception, match="controller disconnected"):
            future.result()

    def test_receivedMessage_sets_result(self, controller):
        """Test receivedMessage sets future result."""
        future = asyncio.Future()
        controller._requests = {"1": future}

        msg = {"response": "200", "data": "test"}
        controller.receivedMessage("1", "Test", "200", msg)

        assert future.done()
        assert future.result() == msg
        assert "1" not in controller._requests

    def test_receivedMessage_sets_exception(self, controller):
        """Test receivedMessage sets exception on error."""
        future = asyncio.Future()
        controller._requests = {"1": future}

        msg = {"response": "400"}
        controller.receivedMessage("1", "Test", "400", msg)

        assert future.done()
        with pytest.raises(CommandError) as exc_info:
            future.result()
        assert exc_info.value.errorCode == "400"

    def test_receivedMessage_notification(self, controller):
        """Test receivedMessage handles notification."""
        # Notification has no response field
        msg = {"command": "NotifyList"}
        controller.receivedMessage("1", "NotifyList", None, msg)

        # Should not raise error
        assert True

    def test_requestChanges(self, controller):
        """Test requestChanges."""
        controller._protocol = Mock()
        controller._protocol.sendCmd = Mock(return_value="1")

        controller.requestChanges("CIRCUIT1", {"STATUS": "ON"})

        controller._protocol.sendCmd.assert_called_once()
        call_args = controller._protocol.sendCmd.call_args
        assert call_args[0][0] == "SETPARAMLIST"
        assert "objectList" in call_args[0][1]


class TestModelController:
    """Test ModelController class."""

    @pytest.fixture
    def model(self):
        """Create a PoolModel instance."""
        return PoolModel()

    @pytest.fixture
    def controller(self, model):
        """Create a ModelController instance."""
        loop = asyncio.get_event_loop()
        return ModelController("192.168.1.100", model, 6681, loop)

    def test_init(self, controller, model):
        """Test ModelController initialization."""
        assert controller.model == model
        assert controller._updatedCallback is None

    async def test_start_loads_objects(self, controller):
        """Test start loads objects into model."""
        with patch.object(BaseController, "start") as mock_base_start, patch.object(
            controller, "getAllObjects"
        ) as mock_get_all, patch.object(controller, "sendCmd") as mock_send_cmd:
            # Mock base start
            mock_base_start.return_value = None

            # Mock getAllObjects
            mock_get_all.return_value = [
                {
                    "objnam": "CIRCUIT1",
                    "params": {
                        "OBJTYP": "CIRCUIT",
                        "SUBTYP": "LIGHT",
                        "SNAME": "Pool Light",
                    },
                }
            ]

            # Mock RequestParamList responses
            mock_send_cmd.return_value = asyncio.Future()
            mock_send_cmd.return_value.set_result({"objectList": []})

            await controller.start()

            # Model should have objects
            assert controller.model.numObjects > 0

    def test_receivedNotifyList(self, controller):
        """Test receivedNotifyList updates model."""
        # Add object to model
        controller.model.addObject(
            "CIRCUIT1",
            {
                "OBJTYP": "CIRCUIT",
                "SUBTYP": "LIGHT",
                "SNAME": "Pool Light",
                "STATUS": "OFF",
            },
        )

        # Receive update
        changes = [{"objnam": "CIRCUIT1", "params": {"STATUS": "ON"}}]
        controller.receivedNotifyList(changes)

        # Object should be updated
        obj = controller.model["CIRCUIT1"]
        assert obj["STATUS"] == "ON"

    def test_receivedNotifyList_calls_callback(self, controller):
        """Test receivedNotifyList calls update callback."""
        callback_called = False
        received_updates = None

        def update_callback(ctrl, updates):
            nonlocal callback_called, received_updates
            callback_called = True
            received_updates = updates

        controller._updatedCallback = update_callback

        # Add object to model
        controller.model.addObject(
            "CIRCUIT1",
            {
                "OBJTYP": "CIRCUIT",
                "SUBTYP": "LIGHT",
                "SNAME": "Pool Light",
                "STATUS": "OFF",
            },
        )

        # Receive update
        changes = [{"objnam": "CIRCUIT1", "params": {"STATUS": "ON"}}]
        controller.receivedNotifyList(changes)

        assert callback_called
        assert "CIRCUIT1" in received_updates
        assert received_updates["CIRCUIT1"]["STATUS"] == "ON"


class TestConnectionHandler:
    """Test ConnectionHandler class."""

    @pytest.fixture
    def mock_controller(self):
        """Create mock controller."""
        controller = Mock()
        controller.start = AsyncMock()
        controller.stop = Mock()
        controller.host = "192.168.1.100"
        return controller

    @pytest.fixture
    def handler(self, mock_controller):
        """Create ConnectionHandler instance."""
        return ConnectionHandler(mock_controller, timeBetweenReconnects=1)

    async def test_init(self, handler, mock_controller):
        """Test ConnectionHandler initialization."""
        assert handler.controller == mock_controller
        assert handler._timeBetweenReconnects == 1
        assert handler._firstTime is True
        assert handler._stopped is False

    async def test_start_connects(self, handler, mock_controller):
        """Test start connects controller."""
        started_called = False

        def on_started(controller):
            nonlocal started_called
            started_called = True

        handler.started = on_started

        await handler.start()
        await asyncio.sleep(0.2)

        mock_controller.start.assert_called()
        assert started_called

        # Cleanup
        handler.stop()

    async def test_reconnect_on_failure(self, handler, mock_controller):
        """Test reconnection on connection failure."""
        # First attempt fails, second succeeds
        mock_controller.start.side_effect = [Exception("Connection failed"), None]

        retrying_called = False

        def on_retrying(delay):
            nonlocal retrying_called
            retrying_called = True

        handler.retrying = on_retrying

        await handler.start()
        await asyncio.sleep(2)

        # Should have retried
        assert retrying_called
        assert mock_controller.start.call_count >= 2

        # Cleanup
        handler.stop()

    async def test_reconnect_on_disconnect(self, handler, mock_controller):
        """Test reconnection on disconnect."""
        # Setup handler
        await handler.start()
        await asyncio.sleep(0.1)

        reconnected_called = False

        def on_reconnected(controller):
            nonlocal reconnected_called
            reconnected_called = True

        handler.reconnected = on_reconnected

        # Simulate disconnect
        handler._diconnectedCallback(mock_controller, None)
        await asyncio.sleep(1.5)

        # Should reconnect
        assert reconnected_called or mock_controller.start.call_count >= 2

        # Cleanup
        handler.stop()

    async def test_debounced_disconnect_notification(self, handler, mock_controller):
        """Test disconnect notification is debounced."""
        # Setup handler
        await handler.start()
        await asyncio.sleep(0.1)

        disconnected_called = False

        def on_disconnected(controller, exc):
            nonlocal disconnected_called
            disconnected_called = True

        handler.disconnected = on_disconnected

        # Simulate disconnect
        handler._diconnectedCallback(mock_controller, None)

        # Immediately after disconnect, callback should not be called
        await asyncio.sleep(0.1)
        # Give some time but not full debounce time

        # After debounce time, callback should be called
        await asyncio.sleep(handler._disconnectDebounceTime + 0.5)
        assert disconnected_called or handler._isConnected

        # Cleanup
        handler.stop()

    async def test_stop(self, handler, mock_controller):
        """Test stopping handler."""
        await handler.start()
        await asyncio.sleep(0.1)

        handler.stop()

        assert handler._stopped is True
        mock_controller.stop.assert_called()

    async def test_exponential_backoff(self, handler):
        """Test exponential backoff calculation."""
        delay1 = handler._next_delay(10)
        delay2 = handler._next_delay(delay1)
        delay3 = handler._next_delay(delay2)

        # Should increase exponentially
        assert delay1 == 15  # 10 * 1.5
        assert delay2 == 22  # 15 * 1.5 (rounded)
        assert delay3 == 33  # 22 * 1.5 (rounded)
