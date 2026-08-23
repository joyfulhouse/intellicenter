"""Test the Pentair IntelliCenter integration initialization."""

import asyncio
import errno
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from pyintellicenter import ICCommandError, ICConnectionError, ICTimeoutError
import pytest

from custom_components.intellicenter import (
    PLATFORMS,
    OnOffControlMixin,
    PoolEntity,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.intellicenter.coordinator import IntelliCenterCoordinator

pytestmark = pytest.mark.asyncio


async def test_async_setup(hass: HomeAssistant) -> None:
    """Test the async_setup function."""
    result = await async_setup(hass, {})
    assert result is True


async def test_async_setup_entry_success(
    hass: HomeAssistant, mock_model_controller: MagicMock
) -> None:
    """Test successful setup of a config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = {CONF_HOST: "192.168.1.100"}
    entry.options = {}  # No custom options, will use defaults
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock()

    # Mock the coordinator's async_start method
    with patch.object(
        IntelliCenterCoordinator,
        "async_start",
        new_callable=AsyncMock,
    ):
        with patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new_callable=AsyncMock,
        ) as mock_forward:
            result = await async_setup_entry(hass, entry)

            assert result is True

            # Verify coordinator is stored in runtime_data
            assert entry.runtime_data is not None
            assert isinstance(entry.runtime_data, IntelliCenterCoordinator)

            # Wait a bit for the async task to complete
            await hass.async_block_till_done()

            # Verify platforms were set up
            mock_forward.assert_called_once_with(entry, PLATFORMS)


@pytest.mark.parametrize(
    ("exc", "expected_exc"),
    [
        # Transient connection failures -> ConfigEntryNotReady so HA retries with
        # backoff (issue #41). pyintellicenter surfaces transport problems as
        # ICConnectionError/ICTimeoutError, but ICConnectionHandler.start() can also
        # re-raise a raw OSError/TimeoutError from the first attempt, so builtin
        # connection/timeout errors and network-errno OSErrors are transient too.
        (ICConnectionError("connection refused"), ConfigEntryNotReady),
        (ICTimeoutError("request timed out"), ConfigEntryNotReady),
        (OSError(errno.EHOSTUNREACH, "no route to host"), ConfigEntryNotReady),
        (ConnectionResetError("connection reset by peer"), ConfigEntryNotReady),
        (TimeoutError(), ConfigEntryNotReady),
        # Permanent faults -> propagate as setup_error instead of retrying forever:
        # a rejected command (protocol/firmware fault), a non-network OSError, or an
        # unrelated programming error.
        (ICCommandError("404"), ICCommandError),
        (PermissionError(errno.EACCES, "permission denied"), PermissionError),
        (OSError(errno.ENOSPC, "no space left on device"), OSError),
        (ValueError("boom"), ValueError),
        # Cancellation must clean up too: CancelledError is a BaseException that
        # bypasses `except Exception`, so cleanup must live in the finally.
        (asyncio.CancelledError(), asyncio.CancelledError),
    ],
    ids=[
        "transient-ICConnectionError",
        "transient-ICTimeoutError",
        "transient-OSError-EHOSTUNREACH",
        "transient-ConnectionResetError",
        "transient-TimeoutError",
        "permanent-ICCommandError",
        "permanent-PermissionError",
        "permanent-OSError-ENOSPC",
        "permanent-ValueError",
        "cancelled-CancelledError",
    ],
)
async def test_async_setup_entry_start_failure(
    hass: HomeAssistant, exc: BaseException, expected_exc: type[BaseException]
) -> None:
    """A failing or cancelled async_start() is classified, and the partial coordinator
    is always torn down (cleanup lives in a finally) with no entry state left.

    Transient connection failures raise ConfigEntryNotReady so HA retries with backoff
    (issue #41); everything else propagates unchanged — a rejected command or
    non-network OSError as a permanent setup_error, a programming error as-is, and
    CancelledError preserved. Either way async_stop() must run, platforms must not be
    forwarded, and runtime_data must be untouched.
    """
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = {CONF_HOST: "192.168.1.100"}
    entry.options = {}  # No custom options, will use defaults
    entry.runtime_data = "UNSET"  # sentinel: must remain unchanged on failure

    with (
        patch.object(
            IntelliCenterCoordinator,
            "async_start",
            new_callable=AsyncMock,
            side_effect=exc,
        ),
        patch.object(
            IntelliCenterCoordinator,
            "async_stop",
            new_callable=AsyncMock,
        ) as mock_stop,
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new_callable=AsyncMock,
        ) as mock_forward,
        pytest.raises(expected_exc),
    ):
        await async_setup_entry(hass, entry)

    # Cleanup is decoupled from classification: the partially started coordinator must
    # be torn down on BOTH the transient and permanent paths so its
    # EVENT_HOMEASSISTANT_STOP listener and pyintellicenter reconnect task don't leak.
    mock_stop.assert_awaited_once()
    mock_forward.assert_not_called()
    assert entry.runtime_data == "UNSET"


async def test_async_setup_entry_post_connect_failure_cleans_up(
    hass: HomeAssistant,
) -> None:
    """A failure after the connection succeeds still stops the coordinator.

    async_start() succeeds (so the reconnect task + HA-stop listener are running), then
    platform forwarding raises. HA does not unload an entry whose setup raised, so
    async_setup_entry itself must tear the coordinator down or the reconnect loop leaks.
    """
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = {CONF_HOST: "192.168.1.100"}
    entry.options = {}
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock()

    with (
        patch.object(IntelliCenterCoordinator, "async_start", new_callable=AsyncMock),
        patch.object(
            IntelliCenterCoordinator,
            "async_stop",
            new_callable=AsyncMock,
        ) as mock_stop,
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new_callable=AsyncMock,
            side_effect=RuntimeError("platform setup failed"),
        ),
        pytest.raises(RuntimeError),
    ):
        await async_setup_entry(hass, entry)

    # Connection succeeded then forwarding failed -> the running coordinator must be
    # stopped so its reconnect task + listener don't leak across HA's setup retries.
    mock_stop.assert_awaited_once()


async def test_async_unload_entry(hass: HomeAssistant) -> None:
    """Test unloading a config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.title = "Test Pool System"
    entry.data = {CONF_HOST: "192.168.1.100"}

    # Set up mock coordinator in runtime_data
    mock_coordinator = MagicMock(spec=IntelliCenterCoordinator)
    mock_coordinator.async_stop = AsyncMock()
    entry.runtime_data = mock_coordinator

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        new_callable=lambda: AsyncMock(return_value=True),
    ) as mock_unload:
        result = await async_unload_entry(hass, entry)

        # Verify async_unload_platforms was called with entry and platforms
        mock_unload.assert_called_once_with(entry, PLATFORMS)

        # Verify coordinator was stopped
        mock_coordinator.async_stop.assert_called_once()

        assert result is True


async def test_async_unload_entry_platforms_fail(hass: HomeAssistant) -> None:
    """Test unload returns False when platforms fail to unload."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.title = "Test Pool System"
    entry.data = {CONF_HOST: "192.168.1.100"}

    # Set up mock coordinator in runtime_data
    mock_coordinator = MagicMock(spec=IntelliCenterCoordinator)
    mock_coordinator.async_stop = AsyncMock()
    entry.runtime_data = mock_coordinator

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        new_callable=lambda: AsyncMock(
            return_value=False
        ),  # Simulate platform unload failure
    ):
        result = await async_unload_entry(hass, entry)

        # Coordinator should still be stopped even if platforms fail
        mock_coordinator.async_stop.assert_called_once()

        # Returns False when platforms fail to unload
        assert result is False


async def test_async_unload_entry_no_runtime_data(hass: HomeAssistant) -> None:
    """Test unload handles missing runtime_data gracefully."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.title = "Test Pool System"
    entry.data = {CONF_HOST: "192.168.1.100"}

    # No runtime_data set
    entry.runtime_data = None

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        new_callable=lambda: AsyncMock(return_value=True),
    ):
        result = await async_unload_entry(hass, entry)

        # Should complete without error
        assert result is True


# -------------------------------------------------------------------------------------
# IntelliCenterCoordinator Tests
# -------------------------------------------------------------------------------------


class TestIntelliCenterCoordinator:
    """Tests for the IntelliCenterCoordinator class."""

    async def test_coordinator_init(self, hass: HomeAssistant) -> None:
        """Test coordinator initialization."""
        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "test_entry_123"
        entry.data = {CONF_HOST: "192.168.1.100"}

        coordinator = IntelliCenterCoordinator(
            hass,
            entry,
            host="192.168.1.100",
            keepalive_interval=90,
            reconnect_delay=30,
        )

        assert coordinator._host == "192.168.1.100"
        assert coordinator._keepalive_interval == 90
        assert coordinator._reconnect_delay == 30
        assert coordinator.connected is False

    async def test_coordinator_async_start_and_stop(self, hass: HomeAssistant) -> None:
        """Test coordinator start and stop."""
        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "test_entry_123"
        entry.data = {CONF_HOST: "192.168.1.100"}

        coordinator = IntelliCenterCoordinator(
            hass,
            entry,
            host="192.168.1.100",
        )

        # Mock the controller
        with patch.object(
            coordinator._controller,
            "start",
            new_callable=AsyncMock,
        ):
            with patch.object(
                coordinator._controller,
                "stop",
                new_callable=AsyncMock,
            ):
                await coordinator.async_start()
                await coordinator.async_stop()

    async def test_coordinator_connected_property(self, hass: HomeAssistant) -> None:
        """Test coordinator connected property."""
        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "test_entry_123"
        entry.data = {CONF_HOST: "192.168.1.100"}

        coordinator = IntelliCenterCoordinator(
            hass,
            entry,
            host="192.168.1.100",
        )

        # Initially not connected
        assert coordinator.connected is False

        # The flag follows the debounced connection callbacks, NOT the
        # handler's ``connected`` property (see the property's docstring for
        # the reconnect callback-ordering hazard).
        coordinator.async_set_connection_state(True)
        assert coordinator.connected is True
        coordinator.async_set_connection_state(False)
        assert coordinator.connected is False

    async def test_coordinator_model_property(self, hass: HomeAssistant) -> None:
        """Test coordinator model property."""
        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "test_entry_123"
        entry.data = {CONF_HOST: "192.168.1.100"}

        coordinator = IntelliCenterCoordinator(
            hass,
            entry,
            host="192.168.1.100",
        )

        # Model should come from controller
        model = coordinator.model
        assert model is not None

    async def test_coordinator_system_info_property(self, hass: HomeAssistant) -> None:
        """Test coordinator system_info property."""
        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "test_entry_123"
        entry.data = {CONF_HOST: "192.168.1.100"}

        coordinator = IntelliCenterCoordinator(
            hass,
            entry,
            host="192.168.1.100",
        )

        # System info should come from controller
        system_info = coordinator.system_info
        # Initially None since controller hasn't started
        assert system_info is None or system_info is coordinator._controller.system_info


# -------------------------------------------------------------------------------------
# Connection-state propagation (regression tests)
# -------------------------------------------------------------------------------------


def _make_started_coordinator(hass: HomeAssistant) -> IntelliCenterCoordinator:
    """Build a real coordinator with two circuits, as if connected and started."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_123"
    entry.data = {CONF_HOST: "192.168.1.100"}

    coordinator = IntelliCenterCoordinator(hass, entry, host="192.168.1.100")
    coordinator.model.add_object(
        "C0001", {"OBJTYP": "CIRCUIT", "SNAME": "Pool Light", "STATUS": "ON"}
    )
    coordinator.model.add_object(
        "C0002", {"OBJTYP": "CIRCUIT", "SNAME": "Spa Jets", "STATUS": "OFF"}
    )
    coordinator._connected = True
    return coordinator


class TestConnectionStatePropagation:
    """Connection-state changes must re-render EVERY entity (finding: stale diff).

    The coordinator's ``data`` holds the last push diff. A connection-state
    change used to fan out with that stale diff still in place, so any entity
    whose attribute was not in it skipped ``async_write_ha_state`` - entities
    stayed "available" with stale values through an outage, or stayed
    "unavailable" after a reconnect.
    """

    async def test_connection_state_change_clears_stale_diff(
        self, hass: HomeAssistant
    ) -> None:
        """async_set_connection_state must clear the last push diff."""
        coordinator = _make_started_coordinator(hass)

        coordinator.async_set_updated_data({"C0001": {"STATUS": "OFF"}})
        assert coordinator.data == {"C0001": {"STATUS": "OFF"}}

        coordinator.async_set_connection_state(False)
        assert coordinator.data == {}
        assert coordinator.connected is False

    async def test_entity_not_in_last_diff_renders_unavailable_on_disconnect(
        self, hass: HomeAssistant
    ) -> None:
        """An entity absent from the last push diff still renders a disconnect."""
        coordinator = _make_started_coordinator(hass)

        c0002 = coordinator.model["C0002"]
        assert c0002 is not None
        entity = PoolEntity(coordinator, c0002)
        entity.async_write_ha_state = MagicMock()  # type: ignore[method-assign]

        # A push for a DIFFERENT object leaves C0002 out of the diff.
        coordinator.async_set_updated_data({"C0001": {"STATUS": "OFF"}})
        entity._handle_coordinator_update()
        entity.async_write_ha_state.assert_not_called()

        # Disconnect: the entity must re-render as unavailable even though it
        # was not named in the last push diff.
        coordinator.async_set_connection_state(False)
        entity._handle_coordinator_update()
        entity.async_write_ha_state.assert_called_once()
        assert entity.available is False

        # Reconnect: it must come back too.
        entity.async_write_ha_state.reset_mock()
        coordinator.async_set_connection_state(True)
        entity._handle_coordinator_update()
        entity.async_write_ha_state.assert_called_once()
        assert entity.available is True

    async def test_connection_event_clears_optimistic_state(
        self, hass: HomeAssistant
    ) -> None:
        """A connection event drops optimistic state (model is source of truth)."""

        class _OnOffEntity(OnOffControlMixin, PoolEntity):
            pass

        coordinator = _make_started_coordinator(hass)
        c0002 = coordinator.model["C0002"]
        assert c0002 is not None
        entity = _OnOffEntity(coordinator, c0002)
        entity.async_write_ha_state = MagicMock()  # type: ignore[method-assign]

        entity._optimistic_state = True
        assert entity.is_on is True  # optimistic, real STATUS is OFF

        coordinator.async_set_connection_state(True)
        entity._handle_coordinator_update()

        assert entity._optimistic_state is None
        assert entity.is_on is False  # back to the model's truth


# -------------------------------------------------------------------------------------
# pyintellicenter 0.2.0 adoption (astop / connected / subscribe / removal entries)
# -------------------------------------------------------------------------------------


class TestPyIntellicenter020Adoption:
    """Coordinator adoption of the pyintellicenter 0.2.0 API surface."""

    async def test_async_stop_awaits_controller_teardown(
        self, hass: HomeAssistant
    ) -> None:
        """async_stop() must not return before the controller is fully stopped.

        The pre-0.2.0 ``handler.stop()`` scheduled the teardown as a
        fire-and-forget task, so ``async_unload_entry`` could complete while
        the connection was still closing. ``astop()`` waits for the real
        teardown.
        """
        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "test_entry_123"
        entry.data = {CONF_HOST: "192.168.1.100"}

        coordinator = IntelliCenterCoordinator(hass, entry, host="192.168.1.100")
        with (
            patch.object(coordinator._controller, "start", new_callable=AsyncMock),
            patch.object(
                coordinator._controller, "stop", new_callable=AsyncMock
            ) as mock_stop,
        ):
            await coordinator.async_start()
            await coordinator.async_stop()
            # The teardown ran to completion INSIDE async_stop, not later.
            mock_stop.assert_awaited_once()
        assert coordinator.connected is False

    async def test_hass_stop_event_awaits_controller_teardown(
        self, hass: HomeAssistant
    ) -> None:
        """The EVENT_HOMEASSISTANT_STOP listener performs the full async stop."""
        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "test_entry_123"
        entry.data = {CONF_HOST: "192.168.1.100"}

        coordinator = IntelliCenterCoordinator(hass, entry, host="192.168.1.100")
        with (
            patch.object(coordinator._controller, "start", new_callable=AsyncMock),
            patch.object(
                coordinator._controller, "stop", new_callable=AsyncMock
            ) as mock_stop,
        ):
            await coordinator.async_start()
            hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
            await hass.async_block_till_done()
            mock_stop.assert_awaited_once()

    async def test_reconnect_callback_ordering_yields_available_entities(
        self, hass: HomeAssistant
    ) -> None:
        """Entities must render available during the on_reconnected fan-out.

        pyintellicenter's ``_starter`` invokes ``on_reconnected`` BEFORE it
        sets the handler's ``_is_connected`` flag, so ``handler.connected`` is
        still False while the reconnect fan-out runs. If the coordinator's
        ``connected`` delegated to that property (an earlier revision of this
        adoption did), every reconnect would render every entity unavailable
        with no later fan-out to correct it. Availability must come from the
        callback-driven coordinator flag.
        """
        coordinator = _make_started_coordinator(hass)
        c0001 = coordinator.model["C0001"]
        assert c0001 is not None
        entity = PoolEntity(coordinator, c0001)
        entity.async_write_ha_state = MagicMock()  # type: ignore[method-assign]

        # Simulate a disconnect that reached the coordinator...
        coordinator._connected = False
        # ...and the library's reconnect callback, delivered while the
        # handler's own flag is still False (the real invocation order).
        coordinator._handler._is_connected = False
        coordinator._handler.on_reconnected(coordinator._controller)

        entity._handle_coordinator_update()
        assert entity.available is True
        entity.async_write_ha_state.assert_called_once()

    async def test_model_updates_flow_through_subscription(
        self, hass: HomeAssistant
    ) -> None:
        """The coordinator receives updates via handler.subscribe(), end to end.

        Drives the REAL library dispatch path (``_notify_updated`` is the
        single site that invokes the legacy callback and all subscribers), so
        this fails if the coordinator's subscription is never registered.
        """
        coordinator = _make_started_coordinator(hass)

        coordinator._controller._notify_updated({"C0001": {"STATUS": "OFF"}})

        assert coordinator.data == {"C0001": {"STATUS": "OFF"}}

    async def test_removal_entry_dispatched_through_subscription(
        self, hass: HomeAssistant
    ) -> None:
        """A ``{objnam: None}`` removal entry from the library reaches the
        coordinator's removal handling via the real dispatch path."""
        coordinator = _make_started_coordinator(hass)
        removed_batches: list[set[str]] = []
        coordinator.async_add_removed_objects_listener(removed_batches.append)

        # The library prunes the model BEFORE dispatching the removal entry.
        coordinator.model.remove_object("C0002")
        coordinator._controller._notify_updated({"C0002": None})

        assert removed_batches == [{"C0002"}]
        assert coordinator.data == {}

    async def test_removal_entry_does_not_crash_entity_update(
        self, hass: HomeAssistant
    ) -> None:
        """The removal fan-out re-renders survivors and skips the doomed entity.

        Before removal filtering, ``PoolEntity.isUpdated`` computed
        ``attribute in updates.get(objnam, {})`` - a removal entry made that
        ``attribute in None`` and raised TypeError. The removed object's own
        entity additionally skips the empty-diff re-render: it is concurrently
        being deleted by the platform's removal listener, and writing one last
        state would resurrect a registry-less ghost.
        """
        coordinator = _make_started_coordinator(hass)
        c0001 = coordinator.model["C0001"]
        c0002 = coordinator.model["C0002"]
        assert c0001 is not None and c0002 is not None
        survivor = PoolEntity(coordinator, c0001)
        doomed = PoolEntity(coordinator, c0002)
        survivor.async_write_ha_state = MagicMock()  # type: ignore[method-assign]
        doomed.async_write_ha_state = MagicMock()  # type: ignore[method-assign]

        coordinator.model.remove_object("C0002")
        coordinator.async_set_updated_data({"C0002": None})

        survivor._handle_coordinator_update()  # must not raise
        doomed._handle_coordinator_update()  # must not raise

        # The diff was cleared of the removal entry, so survivors take the
        # connection-event style re-render; the doomed entity writes nothing.
        survivor.async_write_ha_state.assert_called_once()
        doomed.async_write_ha_state.assert_not_called()

    async def test_mixed_update_filters_removals_from_data(
        self, hass: HomeAssistant
    ) -> None:
        """Removal entries are split out; attribute changes fan out unchanged."""
        coordinator = _make_started_coordinator(hass)
        coordinator._started = True
        coordinator._known_objnams = {"C0001", "C0002"}
        coordinator._pending_redispatch = {"C0002"}
        removed_batches: list[set[str]] = []
        coordinator.async_add_removed_objects_listener(removed_batches.append)

        coordinator.model.remove_object("C0002")
        coordinator.async_set_updated_data({"C0002": None, "C0001": {"STATUS": "OFF"}})

        assert coordinator.data == {"C0001": {"STATUS": "OFF"}}
        assert removed_batches == [{"C0002"}]
        assert "C0002" not in coordinator._known_objnams
        assert coordinator._pending_redispatch == set()
